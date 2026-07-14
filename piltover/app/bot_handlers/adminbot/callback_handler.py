from __future__ import annotations

from piltover.app.bot_handlers.adminbot import actions, pages
from piltover.db.models import MessageRef, Peer
from piltover.tl.types.messages import BotCallbackAnswer


async def adminbot_callback_query_handler(
        peer: Peer, message: MessageRef, data: bytes,
) -> BotCallbackAnswer | None:
    if data == b"adm:home":
        await pages.page_home(peer, message)
        return BotCallbackAnswer(cache_time=0)

    if data == b"adm:stats":
        await pages.page_stats(peer, message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:users:"):
        await pages.page_users(peer, int(data[10:]), message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:admins:"):
        await pages.page_admins(peer, int(data[11:]), message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:channels:"):
        await pages.page_channels(peer, int(data[13:]), message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:groups:"):
        await pages.page_groups(peer, int(data[11:]), message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:user:"):
        await pages.page_user(peer, int(data[9:]), message)
        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"adm:act:admin:"):
        return await actions.toggle_user_admin(peer, message, int(data[14:]), True)

    if data.startswith(b"adm:act:unadmin:"):
        return await actions.toggle_user_admin(peer, message, int(data[16:]), False)

    if data.startswith(b"adm:act:verify:"):
        return await actions.toggle_user_verified(peer, message, int(data[15:]), True)

    if data.startswith(b"adm:act:unverify:"):
        return await actions.toggle_user_verified(peer, message, int(data[17:]), False)

    if data.startswith(b"adm:act:v:ch:"):
        return await actions.toggle_channel_verified(peer, message, int(data[13:]), True)

    if data.startswith(b"adm:act:uv:ch:"):
        return await actions.toggle_channel_verified(peer, message, int(data[14:]), False)

    if data.startswith(b"adm:act:v:g:"):
        return await actions.toggle_chat_verified(peer, message, int(data[12:]), True)

    if data.startswith(b"adm:act:uv:g:"):
        return await actions.toggle_chat_verified(peer, message, int(data[13:]), False)

    if data.startswith(b"adm:act:stars:"):
        _, _, _, user_part, amount_part = data.decode().split(":", 4)
        return await actions.grant_user_stars(peer, message, int(user_part), int(amount_part))

    return None