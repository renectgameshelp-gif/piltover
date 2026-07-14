from __future__ import annotations

from piltover.app.bot_handlers.verifybot import pages
from piltover.app.bot_handlers.verifybot.utils import send_bot_message
from piltover.app.utils import verification
from piltover.db.models import Bot, Channel, Chat, MessageRef, Peer, User
from piltover.tl.types.messages import BotCallbackAnswer


async def _toggle_user(peer: Peer, menu: MessageRef, user_id: int, verified: bool) -> BotCallbackAnswer:
    if user_id == 0:
        user = await User.get(id=peer.owner_id)
    else:
        owned = await Bot.filter(owner_id=peer.owner_id, bot_id=user_id).exists()
        if not owned:
            return BotCallbackAnswer(message="You can only verify your own bots.", alert=True, cache_time=0)
        user = await User.get(id=user_id)

    changed = await verification.set_user_verified(user, verified)
    if user_id == 0:
        await pages.page_self(peer, menu)
    else:
        await pages.page_bots(peer, 0, menu)

    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def _toggle_channel(peer: Peer, menu: MessageRef, channel_id: int, verified: bool) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, creator_id=peer.owner_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Channel not found or not owned by you.", alert=True, cache_time=0)

    changed = await verification.set_channel_verified(channel, verified)
    await pages.page_chats(peer, 0, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def _toggle_chat(peer: Peer, menu: MessageRef, chat_id: int, verified: bool) -> BotCallbackAnswer:
    chat = await Chat.get_or_none(id=chat_id, creator_id=peer.owner_id, deleted=False, migrated=False)
    if chat is None:
        return BotCallbackAnswer(message="Group not found or not owned by you.", alert=True, cache_time=0)

    changed = await verification.set_chat_verified(chat, verified)
    await pages.page_chats(peer, 0, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def verifybot_callback_query_handler(
        peer: Peer, message: MessageRef, data: bytes,
) -> BotCallbackAnswer | None:
    if data == b"page:home":
        await pages.page_home(peer, message)
        return BotCallbackAnswer(cache_time=0)

    if data == b"page:self":
        await pages.page_self(peer, message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"page:bots:"):
        page = int(data[10:])
        await pages.page_bots(peer, page, message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"page:chats:"):
        page = int(data[11:])
        await pages.page_chats(peer, page, message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"act:v:u:"):
        user_id = int(data[8:])
        return await _toggle_user(peer, message, user_id, True)

    if data.startswith(b"act:uv:u:"):
        user_id = int(data[9:])
        return await _toggle_user(peer, message, user_id, False)

    if data.startswith(b"act:v:ch:"):
        channel_id = int(data[9:])
        return await _toggle_channel(peer, message, channel_id, True)

    if data.startswith(b"act:uv:ch:"):
        channel_id = int(data[10:])
        return await _toggle_channel(peer, message, channel_id, False)

    if data.startswith(b"act:v:g:"):
        chat_id = int(data[8:])
        return await _toggle_chat(peer, message, chat_id, True)

    if data.startswith(b"act:uv:g:"):
        chat_id = int(data[9:])
        return await _toggle_chat(peer, message, chat_id, False)

    return None