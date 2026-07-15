from __future__ import annotations

from typing import Any

from piltover.db.enums import PeerType
from piltover.db.models import Channel, Chat, ChatParticipant, Peer, User, Username

BOT_API_CHANNEL_OFFSET = 1_000_000_000_000


def peer_to_bot_api_chat_id(peer: Peer) -> int:
    if peer.type is PeerType.USER:
        return peer.user_id
    if peer.type is PeerType.CHAT:
        return -Chat.make_id_from(peer.chat_id)
    if peer.type is PeerType.CHANNEL:
        return -(BOT_API_CHANNEL_OFFSET + peer.channel_id)
    raise ValueError(f"unsupported peer type: {peer.type}")


def bot_api_chat_id_to_peer_type(chat_id: int) -> PeerType:
    if chat_id > 0:
        return PeerType.USER
    if chat_id <= -BOT_API_CHANNEL_OFFSET:
        return PeerType.CHANNEL
    return PeerType.CHAT


async def _resolve_username_chat_id(username: str) -> int | None:
    resolved = await Username.get_or_none(username=username).select_related("user", "channel")
    if resolved is None:
        return None
    if resolved.channel_id is not None:
        return -(BOT_API_CHANNEL_OFFSET + resolved.channel_id)
    if resolved.user_id is not None:
        return resolved.user_id
    return None


async def resolve_bot_api_peer(bot_user: User, chat_id: Any) -> Peer | None:
    if isinstance(chat_id, str):
        username = chat_id[1:] if chat_id.startswith("@") else chat_id
        resolved_id = await _resolve_username_chat_id(username)
        if resolved_id is None:
            return None
        chat_id = resolved_id

    chat_id = int(chat_id)
    peer_type = bot_api_chat_id_to_peer_type(chat_id)

    if peer_type is PeerType.USER:
        return await Peer.get_or_create_for_user(
            bot_user.id, chat_id, select_related=("user", "user__username"),
        )

    if peer_type is PeerType.CHAT:
        internal_id = Chat.norm_id(abs(chat_id))
        if not await ChatParticipant.filter(
                user_id=bot_user.id, chat_id=internal_id, left=False,
        ).exists():
            return None
        peer, _ = await Peer.get_or_create(
            owner_id=bot_user.id, chat_id=internal_id, type=PeerType.CHAT,
        )
        await peer.fetch_related("chat", "chat__username")
        return peer

    internal_channel_id = abs(chat_id) - BOT_API_CHANNEL_OFFSET
    if not await ChatParticipant.filter(
            user_id=bot_user.id, channel_id=internal_channel_id, left=False,
    ).exists():
        return None
    return await Peer.get_or_none(
        channel_id=internal_channel_id, owner_id__isnull=True, channel__deleted=False,
    ).select_related("channel", "channel__username")


async def peer_is_writable(bot_user: User, peer: Peer) -> bool:
    if peer.type is PeerType.USER:
        return True
    if peer.type is PeerType.CHAT:
        participant = await peer.chat.get_participant(bot_user.id)
        return participant is not None and peer.chat.can_send_plain(participant)
    if peer.type is PeerType.CHANNEL:
        participant = await peer.channel.get_participant(bot_user.id)
        return participant is not None and peer.channel.can_send_messages(participant)
    return False