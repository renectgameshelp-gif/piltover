from typing import cast

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.forum_topics import (
    require_forum_channel, require_manage_topics, get_forum_channel,
    create_forum_topic_record, ensure_general_topic, enable_forum,
    topics_to_tl_bulk, validate_topic_title, build_topics_filter,
    get_topic_by_top_msg,
)
from piltover.db.enums import MessageType, PeerType, ChatAdminRights
from piltover.db.models import User, Channel, Peer, MessageRef, ForumTopic
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import (
    Updates, UpdateChannel, MessageActionTopicEdit, UpdateChannelPinnedTopic,
)
from piltover.tl.functions.channels import (
    ToggleForum, CreateForumTopic, GetForumTopics, GetForumTopicsByID,
    EditForumTopic, UpdatePinnedForumTopic, DeleteTopicHistory,
    ReorderPinnedForumTopics,
)
from piltover.tl.types.messages import ForumTopics, AffectedHistory
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("channels.forum")


@handler.on_request(ToggleForum, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_forum(request: ToggleForum, user_id: int) -> Updates:
    channel, peer = await get_forum_channel(user_id, request.channel)

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    if request.enabled == channel.forum:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    if request.enabled:
        await enable_forum(channel, peer, user_id)
    else:
        channel.forum = False
        await channel.save(update_fields=["forum"])
        from tortoise.expressions import F
        await Channel.filter(id=channel.id).update(version=F("version") + 1)
        await channel.refresh_from_db(["version"])
        await upd.update_channel(channel)

    return Updates(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        users=[],
        chats=[await channel.to_tl()],
    )


@handler.on_request(CreateForumTopic, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def create_forum_topic(request: CreateForumTopic, user_id: int) -> Updates:
    channel, peer = await require_forum_channel(user_id, request.channel)
    await require_manage_topics(user_id, channel)

    title = validate_topic_title(request.title)

    topic, _, updates = await create_forum_topic_record(
        channel, peer, user_id, title,
        icon_color=request.icon_color,
        icon_emoji_id=request.icon_emoji_id,
    )

    updates.updates.insert(0, UpdateChannel(channel_id=channel.make_id()))
    return updates


@handler.on_request(GetForumTopics, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_forum_topics(request: GetForumTopics, user_id: int) -> ForumTopics:
    channel, _ = await require_forum_channel(user_id, request.channel)
    await channel.get_participant_raise(user_id)

    participant = await channel.get_participant(user_id)
    include_hidden = (
        participant is not None
        and channel.admin_has_permission(participant, ChatAdminRights.MANAGE_TOPICS)
    )

    limit = max(min(request.limit, 100), 1)
    topics_filter = build_topics_filter(channel, request.q, request.offset_topic, include_hidden)

    topics = await ForumTopic.filter(topics_filter).order_by("-top_message_id").limit(limit).select_related(
        "top_message", "creator",
    )
    count = await ForumTopic.filter(channel=channel, deleted=False).count()

    topics_tl = await topics_to_tl_bulk(topics, user_id)

    message_refs = [topic.top_message for topic in topics if not topic.deleted]
    messages_tl = await MessageRef.to_tl_bulk_maybecached(message_refs, user_id) if message_refs else []

    ucc = UsersChatsChannels()
    for ref in message_refs:
        ucc.add_message(ref.content_id)
    users, chats, channels = await ucc.resolve()

    return ForumTopics(
        count=count,
        topics=topics_tl,
        messages=messages_tl,
        chats=[*chats, *channels],
        users=users,
        pts=channel.pts,
    )


@handler.on_request(GetForumTopicsByID, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_forum_topics_by_id(request: GetForumTopicsByID, user_id: int) -> ForumTopics:
    channel, _ = await require_forum_channel(user_id, request.channel)
    await channel.get_participant_raise(user_id)

    topics = await ForumTopic.filter(
        channel=channel, topic_id__in=request.topics[:100],
    ).select_related("top_message", "creator")

    topics_tl = await topics_to_tl_bulk(topics, user_id)
    message_refs = [topic.top_message for topic in topics if not topic.deleted]
    messages_tl = await MessageRef.to_tl_bulk_maybecached(message_refs, user_id) if message_refs else []

    ucc = UsersChatsChannels()
    for ref in message_refs:
        ucc.add_message(ref.content_id)
    users, chats, channels = await ucc.resolve()

    return ForumTopics(
        count=len(topics_tl),
        topics=topics_tl,
        messages=messages_tl,
        chats=[*chats, *channels],
        users=users,
        pts=channel.pts,
    )


@handler.on_request(EditForumTopic, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def edit_forum_topic(request: EditForumTopic, user_id: int) -> Updates:
    channel, peer = await require_forum_channel(user_id, request.channel)
    await require_manage_topics(user_id, channel)

    topic = await ForumTopic.get_or_none(channel=channel, topic_id=request.topic_id, deleted=False)
    if topic is None:
        raise ErrorRpc(error_code=400, error_message="TOPIC_ID_INVALID")

    update_fields = []
    action_kwargs: dict = {}

    if request.title is not None:
        topic.title = validate_topic_title(request.title)
        update_fields.append("title")
        action_kwargs["title"] = topic.title
    if request.icon_emoji_id is not None:
        topic.icon_emoji_id = request.icon_emoji_id
        update_fields.append("icon_emoji_id")
        action_kwargs["icon_emoji_id"] = request.icon_emoji_id
    if request.closed is not None:
        topic.closed = request.closed
        update_fields.append("closed")
        action_kwargs["closed"] = request.closed
    if request.hidden is not None:
        topic.hidden = request.hidden
        update_fields.append("hidden")
        action_kwargs["hidden"] = request.hidden

    if not update_fields:
        raise ErrorRpc(error_code=400, error_message="TOPIC_NOT_MODIFIED")

    await topic.save(update_fields=update_fields)

    anchor = await MessageRef.get(id=topic.top_message_id)
    messages = await MessageRef.create_for_peer(
        peer, user_id,
        type=MessageType.SERVICE_TOPIC_EDIT,
        extra_info=MessageActionTopicEdit(**action_kwargs).write(),
        top_message=anchor,
        opposite=False,
    )
    message_ref = messages[peer]
    updates = await upd.send_message_channel(user_id, channel, message_ref)
    updates.updates.insert(0, UpdateChannel(channel_id=channel.make_id()))
    return updates


@handler.on_request(UpdatePinnedForumTopic, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def update_pinned_forum_topic(request: UpdatePinnedForumTopic, user_id: int) -> Updates:
    channel, _ = await require_forum_channel(user_id, request.channel)
    await require_manage_topics(user_id, channel)

    topic = await ForumTopic.get_or_none(channel=channel, topic_id=request.topic_id, deleted=False)
    if topic is None:
        raise ErrorRpc(error_code=400, error_message="TOPIC_ID_INVALID")

    if topic.pinned == request.pinned:
        raise ErrorRpc(error_code=400, error_message="TOPIC_NOT_MODIFIED")

    topic.pinned = request.pinned
    if request.pinned:
        max_index = cast(
            int | None,
            cast(
                object,
                await ForumTopic.filter(channel=channel, pinned=True).order_by("-pinned_index").first()
                .values_list("pinned_index", flat=True)
            ),
        )
        topic.pinned_index = (max_index or 0) + 1
    else:
        topic.pinned_index = None

    await topic.save(update_fields=["pinned", "pinned_index"])

    await upd.update_channel(channel)
    return Updates(
        updates=[
            UpdateChannel(channel_id=channel.make_id()),
            UpdateChannelPinnedTopic(
                channel_id=channel.make_id(),
                topic_id=topic.topic_id,
                pinned=request.pinned,
            ),
        ],
        users=[],
        chats=[await channel.to_tl()],
    )


@handler.on_request(ReorderPinnedForumTopics, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def reorder_pinned_forum_topics(request: ReorderPinnedForumTopics, user_id: int) -> Updates:
    channel, _ = await require_forum_channel(user_id, request.channel)
    await require_manage_topics(user_id, channel)

    async with in_transaction():
        for idx, topic_id in enumerate(request.order):
            await ForumTopic.filter(
                channel=channel, topic_id=topic_id, pinned=True,
            ).update(pinned_index=idx + 1)

    await upd.update_channel(channel)
    return Updates(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        users=[],
        chats=[await channel.to_tl()],
    )


@handler.on_request(DeleteTopicHistory, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def delete_topic_history(request: DeleteTopicHistory, user_id: int) -> AffectedHistory:
    channel, peer = await require_forum_channel(user_id, request.channel)

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    topic = await get_topic_by_top_msg(channel, request.top_msg_id)
    if topic is None:
        raise ErrorRpc(error_code=400, error_message="TOPIC_ID_INVALID")

    to_delete = await MessageRef.filter(
        peer=peer,
    ).filter(
        Q(top_message_id=request.top_msg_id) | Q(id=request.top_msg_id),
    ).exclude(id=request.top_msg_id).values_list("id", flat=True)

    deleted_ids = list(to_delete)
    if deleted_ids:
        async with in_transaction():
            await MessageRef.filter(id__in=deleted_ids).delete()
            await peer.sync_last_message()
        _, pts = await upd.delete_messages_channel(channel, deleted_ids)
    else:
        pts = channel.pts

    return AffectedHistory(pts=pts, pts_count=len(deleted_ids), offset=0)