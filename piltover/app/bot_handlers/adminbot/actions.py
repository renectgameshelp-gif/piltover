from __future__ import annotations

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.adminbot import pages
from piltover.app.utils import verification
from piltover.app.utils.admin_users import LastAdminError, set_user_admin
from piltover.app.utils.stars_manager import grant_stars
from piltover.db.models import Channel, Chat, MessageRef, Peer, User
from piltover.tl.types.messages import BotCallbackAnswer


async def toggle_user_admin(peer: Peer, menu: MessageRef, user_id: int, admin: bool) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    try:
        changed = await set_user_admin(user, admin)
    except LastAdminError as exc:
        return BotCallbackAnswer(message=str(exc), alert=True, cache_time=0)

    await pages.page_user(peer, user_id, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if admin else "revoked"
    return BotCallbackAnswer(message=f"Admin access {action}.", cache_time=0)


async def toggle_user_verified(peer: Peer, menu: MessageRef, user_id: int, verified: bool) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, deleted=False)
    if user is None or user.bot or user.system:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    changed = await verification.set_user_verified(user, verified)
    await pages.page_user(peer, user_id, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def toggle_channel_verified(peer: Peer, menu: MessageRef, channel_id: int, verified: bool) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Channel not found.", alert=True, cache_time=0)

    changed = await verification.set_channel_verified(channel, verified)
    await pages.page_channels(peer, 0, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def toggle_chat_verified(peer: Peer, menu: MessageRef, chat_id: int, verified: bool) -> BotCallbackAnswer:
    chat = await Chat.get_or_none(id=chat_id, deleted=False, migrated=False)
    if chat is None:
        return BotCallbackAnswer(message="Group not found.", alert=True, cache_time=0)

    changed = await verification.set_chat_verified(chat, verified)
    await pages.page_groups(peer, 0, menu)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def grant_user_stars(peer: Peer, menu: MessageRef, user_id: int, amount: int) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    balance = await grant_stars(
        user_id,
        amount,
        title="Admin grant",
        description=f"Granted {amount} stars via @admin",
    )
    await upd.update_stars_balance(user_id, balance.to_stars_amount())
    await pages.page_user(peer, user_id, menu)
    return BotCallbackAnswer(message=f"Granted {amount} stars.", cache_time=0)