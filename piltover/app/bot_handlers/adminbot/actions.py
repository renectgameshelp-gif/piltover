from __future__ import annotations

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.adminbot import pages, pages_extended
from piltover.app.bot_handlers.adminbot.callback_data import (
    encode_stars_wait_data, parse_bot_list_key, parse_user_list_key,
)
from piltover.app.utils import verification
from piltover.app.utils.admin_sessions import kick_all_user_sessions
from piltover.app.utils.admin_users import LastAdminError, set_user_admin
from piltover.app.utils.spam_block import set_user_spam_blocked
from piltover.app.utils.stars_manager import grant_stars, set_stars_balance
from piltover.db.enums import AdminBotState
from piltover.app.utils.admin_channel_ops import (
    admin_delete_bot, delete_channel_admin, kick_channel_member, kick_chat_member,
    promote_channel_admin, promote_chat_admin, transfer_channel_owner, transfer_chat_owner,
)
from piltover.app.utils.admin_delete_user import (
    RestoreAccountError, admin_delete_user, admin_restore_bot, admin_restore_user,
)
from piltover.app.bot_handlers.adminbot.utils import hide_bot_message
from piltover.db.models import AdminBotUserState, AdminReport, Bot, Channel, Chat, MessageRef, Peer, User
from piltover.tl.types.messages import BotCallbackAnswer


async def toggle_user_admin(
        peer: Peer, menu: MessageRef, user_id: int, admin: bool, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    try:
        changed = await set_user_admin(user, admin)
    except LastAdminError as exc:
        return BotCallbackAnswer(message=str(exc), alert=True, cache_time=0)

    await pages.page_user(peer, user_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if admin else "revoked"
    return BotCallbackAnswer(message=f"Admin access {action}.", cache_time=0)


async def toggle_user_verified(
        peer: Peer, menu: MessageRef, user_id: int, verified: bool, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, deleted=False)
    if user is None or user.bot:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    changed = await verification.set_user_verified(user, verified)
    await pages.page_user(peer, user_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def toggle_user_spam_block(
        peer: Peer, menu: MessageRef, user_id: int, blocked: bool, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    changed = await set_user_spam_blocked(user, blocked)
    await pages.page_user(peer, user_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "applied" if blocked else "removed"
    return BotCallbackAnswer(message=f"Spam block {action}.", cache_time=0)


async def kick_user_sessions_action(
        peer: Peer, menu: MessageRef, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    count = await kick_all_user_sessions(user.id)
    await pages.page_user_sessions(peer, user_id, menu, list_key=list_key)
    if count == 0:
        return BotCallbackAnswer(message="No sessions to kick.", cache_time=0)
    return BotCallbackAnswer(message=f"Kicked {count} session(s).", cache_time=0)


async def toggle_channel_verified(
        peer: Peer, menu: MessageRef, channel_id: int, verified: bool, *, list_key: str = "c0",
) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Channel not found.", alert=True, cache_time=0)

    changed = await verification.set_channel_verified(channel, verified)
    await pages_extended.page_channel(peer, channel_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def toggle_chat_verified(
        peer: Peer, menu: MessageRef, chat_id: int, verified: bool, *, list_key: str = "g0",
) -> BotCallbackAnswer:
    chat = await Chat.get_or_none(id=chat_id, deleted=False, migrated=False)
    if chat is None:
        return BotCallbackAnswer(message="Group not found.", alert=True, cache_time=0)

    changed = await verification.set_chat_verified(chat, verified)
    await pages_extended.page_group(peer, chat_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    action = "granted" if verified else "removed"
    return BotCallbackAnswer(message=f"Checkmark {action}.", cache_time=0)


async def grant_user_stars(
        peer: Peer, menu: MessageRef, user_id: int, amount: int, *, list_key: str,
) -> BotCallbackAnswer:
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
    await pages.page_user_stars(peer, user_id, menu, list_key=list_key)
    return BotCallbackAnswer(message=f"Granted {amount} stars.", cache_time=0)


async def set_user_stars(
        peer: Peer, menu: MessageRef, user_id: int, amount: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    balance = await set_stars_balance(
        user_id,
        amount,
        title="Admin set",
        description=f"Balance set to {amount} stars via @admin",
    )
    await upd.update_stars_balance(user_id, balance.to_stars_amount())
    await pages.page_user_stars(peer, user_id, menu, list_key=list_key)
    return BotCallbackAnswer(message=f"Balance set to {amount} stars.", cache_time=0)


async def delete_user_action(
        peer: Peer, menu: MessageRef, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)
    if user.admin and await User.filter(admin=True, bot=False, deleted=False).count() <= 1:
        return BotCallbackAnswer(message="Cannot delete the last admin.", alert=True, cache_time=0)

    if user.system:
        return BotCallbackAnswer(message="Cannot delete a service account.", alert=True, cache_time=0)

    kicked = await admin_delete_user(user)
    page, show_system = parse_user_list_key(list_key)
    await pages.page_users(peer, page, menu, show_system=show_system)
    return BotCallbackAnswer(message=f"User deleted. Kicked {kicked} session(s).", cache_time=0)


async def delete_bot_action(peer: Peer, menu: MessageRef, bot_id: int, *, list_key: str) -> BotCallbackAnswer:
    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    if bot_user.system:
        return BotCallbackAnswer(message="Cannot delete a system bot.", alert=True, cache_time=0)
    await admin_delete_bot(bot_user)
    page, show_system = parse_bot_list_key(list_key)
    await pages_extended.page_bots(peer, page, menu, show_system=show_system)
    return BotCallbackAnswer(message="Bot deleted.", cache_time=0)


async def restore_deleted_account_action(
        peer: Peer, menu: MessageRef, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, deleted=True, system=False)
    if user is None:
        return BotCallbackAnswer(message="Account not found.", alert=True, cache_time=0)

    try:
        if user.bot:
            await admin_restore_bot(user)
            label = "Bot restored."
        else:
            await admin_restore_user(user)
            label = "User restored."
    except RestoreAccountError as exc:
        return BotCallbackAnswer(message=str(exc), alert=True, cache_time=0)

    page = int(list_key[1:]) if list_key.startswith("d") and list_key[1:].isdigit() else 0
    await pages_extended.page_deleted_users(peer, page, menu)
    return BotCallbackAnswer(message=label, cache_time=0)


async def delete_channel_action(
        peer: Peer, menu: MessageRef, channel_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Channel not found.", alert=True, cache_time=0)
    await delete_channel_admin(channel)
    await pages.page_channels(peer, 0, menu)
    return BotCallbackAnswer(message="Channel deleted.", cache_time=0)


async def kick_channel_member_action(
        peer: Peer, menu: MessageRef, channel_id: int, target_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Not found.", alert=True, cache_time=0)
    await kick_channel_member(channel, target_id)
    await pages_extended.page_channel_members(peer, channel_id, 0, menu, list_key=list_key)
    return BotCallbackAnswer(message="Member kicked.", cache_time=0)


async def kick_group_member_action(
        peer: Peer, menu: MessageRef, chat_id: int, target_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    chat = await Chat.get_or_none(id=chat_id, deleted=False)
    if chat is None:
        return BotCallbackAnswer(message="Not found.", alert=True, cache_time=0)
    await kick_chat_member(chat, target_id, actor_id=peer.owner_id)
    await pages_extended.page_group_members(peer, chat_id, 0, menu, list_key=list_key)
    return BotCallbackAnswer(message="Member kicked.", cache_time=0)


async def promote_channel_admin_action(
        peer: Peer, menu: MessageRef, channel_id: int, target_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return BotCallbackAnswer(message="Not found.", alert=True, cache_time=0)
    try:
        await promote_channel_admin(channel, target_id)
    except ValueError:
        return BotCallbackAnswer(message="Not a participant.", alert=True, cache_time=0)
    await pages_extended.page_channel_members(peer, channel_id, 0, menu, list_key=list_key)
    return BotCallbackAnswer(message="Admin rights granted.", cache_time=0)


async def promote_group_admin_action(
        peer: Peer, menu: MessageRef, chat_id: int, target_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    chat = await Chat.get_or_none(id=chat_id, deleted=False)
    if chat is None:
        return BotCallbackAnswer(message="Not found.", alert=True, cache_time=0)
    try:
        await promote_chat_admin(chat, target_id)
    except ValueError:
        return BotCallbackAnswer(message="Not a participant.", alert=True, cache_time=0)
    await pages_extended.page_group_members(peer, chat_id, 0, menu, list_key=list_key)
    return BotCallbackAnswer(message="Admin rights granted.", cache_time=0)


async def toggle_bot_verified(
        peer: Peer, menu: MessageRef, bot_id: int, verified: bool, *, list_key: str,
) -> BotCallbackAnswer:
    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    changed = await verification.set_user_verified(bot_user, verified)
    await pages_extended.page_bot(peer, bot_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    return BotCallbackAnswer(message="Checkmark updated.", cache_time=0)


async def toggle_bot_system(
        peer: Peer, menu: MessageRef, bot_id: int, system: bool, *, list_key: str, confirm: bool = False,
) -> BotCallbackAnswer:
    from piltover.app.utils.admin_access import is_builtin_admin_bot

    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    if not system and await is_builtin_admin_bot(bot_user) and not confirm:
        await pages_extended.page_bot_unsystem_warning(peer, bot_id, menu, list_key=list_key)
        return BotCallbackAnswer(
            message="⚠️ Removing system from @admin breaks built-in handlers.",
            alert=True,
            cache_time=0,
        )
    if bot_user.system == system:
        return BotCallbackAnswer(message="Already up to date.", cache_time=0)
    bot_user.system = system
    await bot_user.save(update_fields=["system", "version"])
    await bot_user.inc_version()
    await upd.update_user(bot_user)
    await pages_extended.page_bot(peer, bot_id, menu, list_key=list_key)
    action = "marked as system" if system else "unmarked as system"
    return BotCallbackAnswer(message=f"Bot {action}.", cache_time=0)


async def revoke_bot_token_action(
        peer: Peer, menu: MessageRef, bot_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    from piltover.db.models.bot import bot_gen_token

    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    bot_row = await Bot.get_or_none(bot_id=bot_id)
    if bot_row is None:
        return BotCallbackAnswer(message="Bot record not found.", alert=True, cache_time=0)

    bot_row.token_nonce = bot_gen_token()
    await bot_row.save(update_fields=["token_nonce"])
    await pages_extended.page_bot_token(peer, bot_id, menu, list_key=list_key)
    return BotCallbackAnswer(message="Token revoked.", cache_time=0)


async def hide_message_action(peer: Peer, menu: MessageRef) -> BotCallbackAnswer:
    await hide_bot_message(peer, menu)
    return BotCallbackAnswer(message="Hidden.", cache_time=0)


async def spam_from_report_action(
        peer: Peer, menu: MessageRef, report_id: int, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    changed = await set_user_spam_blocked(user, True)
    await pages_extended.page_report(peer, report_id, menu, list_key=list_key)
    if not changed:
        return BotCallbackAnswer(message="Already spam blocked.", cache_time=0)
    return BotCallbackAnswer(message="Spam block applied.", cache_time=0)


async def spam_author_from_report_action(
        peer: Peer, menu: MessageRef, report_id: int, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    return await spam_from_report_action(peer, menu, report_id, user_id, list_key=list_key)


async def ban_user_from_report_action(
        peer: Peer, menu: MessageRef, report_id: int, user_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)
    if user.admin and await User.filter(admin=True, bot=False, deleted=False).count() <= 1:
        return BotCallbackAnswer(message="Cannot delete the last admin.", alert=True, cache_time=0)

    kicked = await admin_delete_user(user)
    await pages_extended.page_report(peer, report_id, menu, list_key=list_key)
    return BotCallbackAnswer(message=f"User banned. Kicked {kicked} session(s).", cache_time=0)


async def ban_bot_from_report_action(
        peer: Peer, menu: MessageRef, report_id: int, bot_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    if bot_user.system:
        return BotCallbackAnswer(message="Cannot delete a system bot.", alert=True, cache_time=0)

    await admin_delete_bot(bot_user)
    await pages_extended.page_report(peer, report_id, menu, list_key=list_key)
    return BotCallbackAnswer(message="Bot banned.", cache_time=0)


async def review_report_action(
        peer: Peer, menu: MessageRef, report_id: int, *, list_key: str,
) -> BotCallbackAnswer:
    report = await AdminReport.get_or_none(id=report_id)
    if report is None:
        return BotCallbackAnswer(message="Report not found.", alert=True, cache_time=0)
    report.reviewed = True
    await report.save(update_fields=["reviewed"])
    await pages_extended.page_report(peer, report_id, menu, list_key=list_key)
    return BotCallbackAnswer(message="Marked reviewed.", cache_time=0)


async def begin_search_input(
        peer: Peer, menu: MessageRef, kind: str, *, admin_user_id: int,
) -> BotCallbackAnswer:
    from piltover.app.utils.admin_search import SearchFilters

    filters = SearchFilters(kind=kind)
    await AdminBotUserState.set_state(admin_user_id, AdminBotState.WAIT_SEARCH, filters.encode())
    await pages_extended.page_search_prompt(peer, menu, filters=filters)
    return BotCallbackAnswer(message="Send your search query in chat.", cache_time=0)


async def toggle_search_filter(
        peer: Peer, menu: MessageRef, flag: str, *, admin_user_id: int,
) -> BotCallbackAnswer:
    from piltover.app.utils.admin_search import SearchFilters

    state = await AdminBotUserState.get_or_none(user_id=admin_user_id)
    if state is None or state.state is not AdminBotState.WAIT_SEARCH:
        return BotCallbackAnswer(message="Search session expired.", alert=True, cache_time=0)

    filters = SearchFilters.decode(state.data)
    filters.toggle(flag)
    await AdminBotUserState.set_state(admin_user_id, AdminBotState.WAIT_SEARCH, filters.encode())
    await pages_extended.page_search_prompt(peer, menu, filters=filters)
    return BotCallbackAnswer(cache_time=0)


async def clear_bot_field(
        peer: Peer, menu: MessageRef, bot_id: int, field: str, *, list_key: str, admin_user_id: int,
) -> BotCallbackAnswer:
    from piltover.app.utils.admin_bot_edit import CLEARABLE_BOT_FIELDS, apply_bot_field_value
    from piltover.db.enums import AdminBotState

    if field not in CLEARABLE_BOT_FIELDS:
        return BotCallbackAnswer(message="This field cannot be cleared.", alert=True, cache_time=0)

    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)

    error = await apply_bot_field_value(bot_user, field, "", clear=True)
    if error is not None:
        return BotCallbackAnswer(message=error, alert=True, cache_time=0)

    await AdminBotUserState.filter(user_id=admin_user_id, state=AdminBotState.WAIT_BOT_EDIT).delete()
    await pages_extended.page_bot_settings(peer, bot_id, menu, list_key=list_key)
    return BotCallbackAnswer(message="Cleared.", cache_time=0)


async def begin_bot_edit_input(
        peer: Peer, menu: MessageRef, bot_id: int, field: str, *, list_key: str, admin_user_id: int,
) -> BotCallbackAnswer:
    bot_user = await User.get_or_none(id=bot_id, bot=True, deleted=False)
    if bot_user is None:
        return BotCallbackAnswer(message="Bot not found.", alert=True, cache_time=0)
    if field == "username" and bot_user.system:
        return BotCallbackAnswer(message="System bot username cannot be changed.", alert=True, cache_time=0)

    await AdminBotUserState.set_state(
        admin_user_id,
        AdminBotState.WAIT_BOT_EDIT,
        f"{field}:{bot_id}:{list_key}:{menu.id}".encode(),
    )
    await pages_extended.page_bot_edit_prompt(peer, menu, bot_id, field, list_key=list_key)
    return BotCallbackAnswer(message="Send the new value in chat.", cache_time=0)


async def begin_transfer_owner_input(
        peer: Peer, menu: MessageRef, entity_kind: str, entity_id: int, *, list_key: str, admin_user_id: int,
) -> BotCallbackAnswer:
    from piltover.db.enums import AdminBotState
    await AdminBotUserState.set_state(
        admin_user_id,
        AdminBotState.WAIT_TRANSFER_OWNER,
        f"{entity_kind}:{entity_id}:{list_key}".encode(),
    )
    return BotCallbackAnswer(message="Send new owner user ID in chat.", alert=True, cache_time=0)


async def begin_custom_stars_input(
        peer: Peer, menu: MessageRef, user_id: int, *, list_key: str, admin_user_id: int,
) -> BotCallbackAnswer:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return BotCallbackAnswer(message="User not found.", alert=True, cache_time=0)

    await AdminBotUserState.set_state(
        admin_user_id,
        AdminBotState.WAIT_STARS_AMOUNT,
        encode_stars_wait_data(user_id, list_key),
    )
    await pages.page_user_stars(peer, user_id, menu, list_key=list_key)
    return BotCallbackAnswer(
        message="Send the desired star balance as a number in chat.",
        alert=True,
        cache_time=0,
    )