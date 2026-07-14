from __future__ import annotations

from piltover.app.bot_handlers.adminbot.utils import (
    HOME,
    PAGE_SIZE,
    back_home_row,
    home_keyboard,
    list_keyboard,
    user_label,
)
from piltover.app.bot_handlers.typetestbot.common import edit_bot_message
from piltover.db.models import Channel, Chat, MessageRef, Peer, User, Username
from piltover.tl import KeyboardButtonCallback, KeyboardButtonRow, ReplyInlineMarkup


async def page_home(peer: Peer, menu: MessageRef) -> MessageRef:
    text = (
        "🛡 Admin Panel\n\n"
        "Server administration. Choose a category below."
    )
    return await edit_bot_message(menu, peer, text, home_keyboard())


async def _usernames_for_users(users: list[User]) -> dict[int, str | None]:
    if not users:
        return {}
    user_ids = [user.id for user in users]
    return {
        user_id: username
        for user_id, username in await Username.filter(user_id__in=user_ids).values_list("user_id", "username")
    }


async def page_users(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    users = list(
        await User.filter(bot=False, system=False, deleted=False).order_by("-id")
    )
    total = len(users)
    if total == 0:
        return await edit_bot_message(menu, peer, "No users found.", list_keyboard(
            items=[], page=0, total_pages=1, page_prefix=b"adm:users",
        ))

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = users[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    usernames = await _usernames_for_users(chunk)

    items = [
        (user_label(user, username=usernames.get(user.id)), f"adm:user:{user.id}".encode())
        for user in chunk
    ]
    text = f"Users ({total}). Tap to manage:"
    keyboard = list_keyboard(items=items, page=page, total_pages=total_pages, page_prefix=b"adm:users")
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_admins(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    users = list(await User.filter(admin=True, bot=False, deleted=False).order_by("-id"))
    total = len(users)
    if total == 0:
        return await edit_bot_message(menu, peer, "No admins found.", list_keyboard(
            items=[], page=0, total_pages=1, page_prefix=b"adm:admins", back_data=HOME,
        ))

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = users[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    usernames = await _usernames_for_users(chunk)

    items = [
        (user_label(user, username=usernames.get(user.id)), f"adm:user:{user.id}".encode())
        for user in chunk
    ]
    text = f"Admins ({total}). Tap to manage:"
    keyboard = list_keyboard(items=items, page=page, total_pages=total_pages, page_prefix=b"adm:admins")
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_channels(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    channels = list(await Channel.filter(deleted=False).order_by("-id"))
    total = len(channels)
    if total == 0:
        return await edit_bot_message(menu, peer, "No channels.", list_keyboard(
            items=[], page=0, total_pages=1, page_prefix=b"adm:channels",
        ))

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = channels[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    items: list[tuple[str, bytes]] = []
    for channel in chunk:
        kind = "channel" if channel.channel else "supergroup"
        badge = " ✓" if channel.verified else ""
        label = f"[{kind}] {channel.name}{badge}"
        if channel.verified:
            data = f"adm:act:uv:ch:{channel.id}".encode()
        else:
            data = f"adm:act:v:ch:{channel.id}".encode()
        items.append((label[:64], data))

    text = f"Channels & supergroups ({total}). Tap to toggle verified:"
    keyboard = list_keyboard(items=items, page=page, total_pages=total_pages, page_prefix=b"adm:channels")
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_groups(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    chats = list(await Chat.filter(deleted=False, migrated=False).order_by("-id"))
    total = len(chats)
    if total == 0:
        return await edit_bot_message(menu, peer, "No basic groups.", list_keyboard(
            items=[], page=0, total_pages=1, page_prefix=b"adm:groups",
        ))

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = chats[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    items: list[tuple[str, bytes]] = []
    for chat in chunk:
        badge = " ✓" if chat.verified else ""
        label = f"[group] {chat.name}{badge}"
        if chat.verified:
            data = f"adm:act:uv:g:{chat.id}".encode()
        else:
            data = f"adm:act:v:g:{chat.id}".encode()
        items.append((label[:64], data))

    text = f"Basic groups ({total}). Tap to toggle verified:"
    keyboard = list_keyboard(items=items, page=page, total_pages=total_pages, page_prefix=b"adm:groups")
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_stats(peer: Peer, menu: MessageRef) -> MessageRef:
    users = await User.filter(bot=False, system=False, deleted=False).count()
    bots = await User.filter(bot=True, system=False, deleted=False).count()
    admins = await User.filter(admin=True, bot=False, deleted=False).count()
    channels = await Channel.filter(deleted=False, channel=True).count()
    supergroups = await Channel.filter(deleted=False, supergroup=True).count()
    groups = await Chat.filter(deleted=False, migrated=False).count()
    verified_users = await User.filter(verified=True, deleted=False).count()

    text = (
        "📊 Server statistics\n\n"
        f"Users: {users}\n"
        f"Bots: {bots}\n"
        f"Admins: {admins}\n"
        f"Verified users: {verified_users}\n"
        f"Channels: {channels}\n"
        f"Supergroups: {supergroups}\n"
        f"Basic groups: {groups}"
    )
    keyboard = ReplyInlineMarkup(rows=[back_home_row()])
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_user(peer: Peer, user_id: int, menu: MessageRef) -> MessageRef:
    user = await User.get_or_none(id=user_id, bot=False, system=False, deleted=False)
    if user is None:
        return await edit_bot_message(menu, peer, "User not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    username = await user.get_raw_username()
    lines = [
        f"👤 {user.first_name}" + (f" {user.last_name}" if user.last_name else ""),
        f"ID: {user.id}",
    ]
    if username:
        lines.append(f"Username: @{username}")
    if user.phone_number:
        lines.append(f"Phone: {user.phone_number}")
    lines.append(f"Admin: {'yes' if user.admin else 'no'}")
    lines.append(f"Verified: {'yes' if user.verified else 'no'}")

    rows: list[KeyboardButtonRow] = []
    if user.admin:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Revoke admin", data=f"adm:act:unadmin:{user.id}".encode()),
        ]))
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Grant admin", data=f"adm:act:admin:{user.id}".encode()),
        ]))

    if user.verified:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Remove checkmark", data=f"adm:act:unverify:{user.id}".encode()),
        ]))
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Grant checkmark", data=f"adm:act:verify:{user.id}".encode()),
        ]))

    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="+25 ⭐", data=f"adm:act:stars:{user.id}:25".encode()),
        KeyboardButtonCallback(text="+100 ⭐", data=f"adm:act:stars:{user.id}:100".encode()),
    ]))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Users", data=b"adm:users:0"),
        KeyboardButtonCallback(text="« Main menu", data=HOME),
    ]))

    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))