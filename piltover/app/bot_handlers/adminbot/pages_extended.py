from __future__ import annotations

from piltover.app.bot_handlers.adminbot.callback_data import (
    bot_open_link,
    bots_list_callback,
    encode_bot_list_key,
    encode_list_key,
    parse_bot_list_key,
    user_link,
    user_open_link,
)
from piltover.app.bot_handlers.adminbot.pages import _usernames_for_users, _user_nav_row
from piltover.app.bot_handlers.adminbot.utils import (
    HOME, PAGE_SIZE, back_home_row, hide_row, list_keyboard, push_bot_message,
)
from piltover.app.utils.admin_reports import (
    build_report_detail_lines, format_peer_type, format_report_reason, get_report_context,
)
from piltover.app.bot_handlers.typetestbot.common import edit_bot_message
from piltover.db.enums import AdminReportPeerType
from piltover.db.models import (
    AdminReport, Bot, BotCommand, BotInfo, Channel, Chat, ChatParticipant, MessageRef, Peer, User, Username,
)
from piltover.tl import KeyboardButtonCallback, KeyboardButtonRow, ReplyInlineMarkup


async def page_search_prompt(peer: Peer, menu: MessageRef, *, filters) -> MessageRef:
    labels = {
        "user": "user (ID, @username, phone, or name)",
        "ch": "channel/supergroup (ID or @username)",
        "gr": "basic group (ID)",
        "bot": "bot (ID or @username)",
    }
    lines = [f"🔍 Send {labels.get(filters.kind, 'query')} in chat.", ""]
    rows: list[KeyboardButtonRow] = []

    if filters.kind == "user":
        lines.append("Filters:")
        lines.append(f"  System users: {'yes' if filters.show_system else 'no'}")
        lines.append(f"  Deleted users: {'yes' if filters.include_deleted else 'no'}")
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="✅ System" if filters.show_system else "☑️ System",
                data=b"adm:findf:sys",
            ),
            KeyboardButtonCallback(
                text="✅ Deleted" if filters.include_deleted else "☑️ Deleted",
                data=b"adm:findf:del",
            ),
        ]))
    elif filters.kind == "bot":
        lines.append("Filters:")
        lines.append(f"  System bots: {'yes' if filters.show_system else 'no'}")
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="✅ System" if filters.show_system else "☑️ System",
                data=b"adm:findf:sys",
            ),
        ]))
    elif filters.kind == "ch":
        kind_labels = {"all": "all", "channel": "channels only", "supergroup": "supergroups only"}
        lines.append("Filters:")
        lines.append(f"  Type: {kind_labels.get(filters.channel_kind, filters.channel_kind)}")
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Cycle type", data=b"adm:findf:channel"),
        ]))

    rows.append(back_home_row())
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_bot_edit_prompt(
        peer: Peer, menu: MessageRef, bot_id: int, field: str, *, list_key: str = "b0",
) -> MessageRef:
    from piltover.app.utils.admin_bot_edit import CLEARABLE_BOT_FIELDS

    prompts = {
        "name": "Send new bot name (max 64 characters).",
        "lastname": "Send last name (max 64) or tap Empty to clear.",
        "username": "Send @username (5–32 chars: a-z, 0-9, _).",
        "about": "Send about text (max 120) or tap Empty to clear.",
        "desc": "Send bot description (max 120) or tap Empty to clear.",
        "privacy": "Send privacy policy https URL (max 240) or tap Empty to clear.",
    }
    title = prompts.get(field, "Send new value.")
    rows: list[KeyboardButtonRow] = []
    if field in CLEARABLE_BOT_FIELDS:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Empty", data=f"adm:bot:empty:{field}:{bot_id}:{list_key}".encode()),
        ]))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Cancel", data=f"adm:bot:set:{bot_id}:{list_key}".encode()),
    ]))
    return await edit_bot_message(menu, peer, f"✏️ {title}", ReplyInlineMarkup(rows=rows))


async def page_deleted_users(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    accounts = list(await User.filter(deleted=True, system=False).order_by("-id"))
    total = len(accounts)
    if total == 0:
        return await edit_bot_message(menu, peer, "No deleted accounts.", list_keyboard(
            items=[], page=0, total_pages=1, page_prefix=b"adm:del",
        ))

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = accounts[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    items = [
        (
            f"{'🤖' if u.bot else '🗑'} {u.first_name} (id {u.id})",
            f"adm:delu:{u.id}:d{page}".encode(),
        )
        for u in chunk
    ]
    return await edit_bot_message(
        menu, peer, f"Deleted accounts ({total}):", list_keyboard(
            items=items, page=page, total_pages=total_pages, page_prefix=b"adm:del",
        ),
    )


async def page_deleted_user(peer: Peer, user_id: int, menu: MessageRef, *, list_key: str = "d0") -> MessageRef:
    user = await User.get_or_none(id=user_id, deleted=True, system=False)
    if user is None:
        return await edit_bot_message(menu, peer, "Account not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    from piltover.db.models import BlockedPhone, DeletedAccountSnapshot
    blocked = await BlockedPhone.get_or_none(user_id=user.id)
    snapshot = await DeletedAccountSnapshot.get_or_none(user_id=user.id)

    kind = "bot" if user.bot else "user"
    lines = [
        f"{'🤖' if user.bot else '🗑'} Deleted {kind}",
        f"ID: {user.id}",
        f"Name: {user.first_name}",
        f"Snapshot: {'yes' if snapshot else 'no'}",
    ]
    if snapshot:
        if snapshot.username:
            lines.append(f"Saved username: @{snapshot.username}")
        if snapshot.phone_number:
            lines.append(f"Saved phone: {snapshot.phone_number}")
        if user.bot and snapshot.bot_owner_id:
            lines.append(f"Saved owner id: {snapshot.bot_owner_id}")
    if not user.bot:
        lines.append(f"Phone blocked: {'yes' if blocked else 'no'}")
        if blocked:
            lines.append(f"Blocked phone: {blocked.phone_number}")

    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="♻️ Restore account",
                data=f"adm:act:restore:{user.id}:{list_key}".encode(),
            ),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Deleted list", data=f"adm:del:{list_key[1:]}".encode()),
            KeyboardButtonCallback(text="« Main menu", data=HOME),
        ]),
    ]
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


def _bot_label(user: User, *, username: str | None = None) -> str:
    badges: list[str] = []
    if user.system:
        badges.append("⚙")
    if user.verified:
        badges.append("✓")
    badge = "".join(badges)
    prefix = f"{badge} " if badge else ""
    un = f"@{username}" if username else "—"
    name = f"{prefix}🤖 {user.first_name} ({un})"
    return name[:64]


def _bot_back_row(list_key: str) -> KeyboardButtonRow:
    page, show_system = parse_bot_list_key(list_key)
    return KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Bots", data=bots_list_callback(page, show_system=show_system)),
        KeyboardButtonCallback(text="« Main menu", data=HOME),
    ])


async def _get_bot_user(bot_id: int) -> User | None:
    return await User.get_or_none(id=bot_id, bot=True, deleted=False)


async def page_bots(peer: Peer, page: int, menu: MessageRef, *, show_system: bool = False) -> MessageRef:
    query = User.filter(bot=True, deleted=False)
    if not show_system:
        query = query.filter(system=False)
    bots = list(await query.order_by("-system", "-id"))
    total = len(bots)
    list_key = encode_bot_list_key(page, show_system=show_system)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    page = max(0, min(page, total_pages - 1))
    list_key = encode_bot_list_key(page, show_system=show_system)
    chunk = bots[page * PAGE_SIZE:(page + 1) * PAGE_SIZE] if total else []
    usernames = await _usernames_for_users(chunk)

    scope = "all bots" if show_system else "user bots"
    text = f"🤖 Bots ({total}, {scope}). Tap to manage:"
    items = [
        (_bot_label(u, username=usernames.get(u.id)), f"adm:bot:{u.id}:{list_key}".encode())
        for u in chunk
    ]

    page_prefix = b"adm:bots:sys" if show_system else b"adm:bots"
    keyboard = list_keyboard(
        items=items, page=page, total_pages=total_pages, page_prefix=page_prefix,
    )
    toggle_label = "✅ Show system" if show_system else "☑️ Show system"
    keyboard.rows.insert(0, KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="🔍 Find bot", data=b"adm:find:bot"),
        KeyboardButtonCallback(text=toggle_label, data=bots_list_callback(page, show_system=not show_system)),
    ]))
    if total == 0:
        text = f"🤖 No bots ({scope})."
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_bot_unsystem_warning(
        peer: Peer, bot_id: int, menu: MessageRef, *, list_key: str = "b0",
) -> MessageRef:
    username = await Username.filter(user_id=bot_id).first().values_list("username", flat=True)
    handle = f"@{username}" if username else f"bot {bot_id}"
    lines = [
        f"⚠️ Warning — {handle}",
        "",
        "Removing the system flag from @admin will break built-in handlers:",
        "• Inline button callbacks stop routing to the admin panel",
        "• Outgoing messages to the bot use a different delivery path",
        "",
        "You will lose the admin panel until the system flag is restored.",
    ]
    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="Yes, remove system flag",
                data=f"adm:act:unsystemok:bot:{bot_id}:{list_key}".encode(),
            ),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Cancel", data=f"adm:bot:{bot_id}:{list_key}".encode()),
        ]),
    ]
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_bot(
        peer: Peer, bot_id: int, menu: MessageRef, *, list_key: str = "b0",
        overlay: bool = False, new_message: bool = False,
) -> MessageRef:
    bot_user = await _get_bot_user(bot_id)
    if bot_user is None:
        markup = ReplyInlineMarkup(rows=[back_home_row()])
        if overlay or new_message:
            return await push_bot_message(peer, "Bot not found.", markup)
        return await edit_bot_message(menu, peer, "Bot not found.", markup)

    username = await bot_user.get_raw_username()
    bot_row = await Bot.get_or_none(bot_id=bot_id).select_related("owner")
    owner = bot_row.owner if bot_row else None
    commands_count = await BotCommand.filter(bot_id=bot_id).count()
    info = await BotInfo.get_or_none(user_id=bot_id)

    display_name = bot_user.first_name
    if bot_user.last_name:
        display_name = f"{display_name} {bot_user.last_name}"

    lines = [
        f"🤖 {display_name}",
        f"ID: {bot_user.id}",
        f"Username: @{username}" if username else "Username: —",
        f"Verified: {'yes ✓' if bot_user.verified else 'no'}",
        f"System: {'yes ⚙' if bot_user.system else 'no'}",
        f"Commands: {commands_count}",
    ]
    if bot_user.about:
        lines.append(f"About: {bot_user.about[:100]}")
    if info and info.description:
        lines.append(f"Description: {info.description[:100]}")
    if owner:
        lines.append(f"Owner: {owner.first_name} (id {owner.id})")
    elif bot_user.system:
        lines.append("Owner: — (system bot)")

    rows: list[KeyboardButtonRow] = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="🔑 API token", data=f"adm:bot:token:{bot_id}:{list_key}".encode()),
            KeyboardButtonCallback(text="⚙️ Settings", data=f"adm:bot:set:{bot_id}:{list_key}".encode()),
        ]),
    ]
    owner_row: list[KeyboardButtonCallback] = []
    if owner:
        owner_row.append(KeyboardButtonCallback(text="👤 Owner", data=user_link(owner.id, list_key)))
    if bot_user.verified:
        owner_row.append(KeyboardButtonCallback(
            text="Remove ✓", data=f"adm:act:unverify:bot:{bot_id}:{list_key}".encode(),
        ))
    else:
        owner_row.append(KeyboardButtonCallback(
            text="Grant ✓", data=f"adm:act:verify:bot:{bot_id}:{list_key}".encode(),
        ))
    if owner_row:
        rows.append(KeyboardButtonRow(buttons=owner_row))

    if bot_user.system:
        from piltover.app.utils.admin_access import is_builtin_admin_bot

        unsystem_label = "⚠️ Remove system flag" if await is_builtin_admin_bot(bot_user) else "Remove system flag"
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text=unsystem_label, data=f"adm:act:unsystem:bot:{bot_id}:{list_key}".encode()),
        ]))
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Mark as system", data=f"adm:act:system:bot:{bot_id}:{list_key}".encode()),
            KeyboardButtonCallback(text="🗑 Delete", data=f"adm:act:delbot:{bot_id}:{list_key}".encode()),
        ]))
    if overlay:
        rows.append(hide_row())
    else:
        rows.append(_bot_back_row(list_key))
    markup = ReplyInlineMarkup(rows=rows)
    if overlay or new_message:
        return await push_bot_message(peer, "\n".join(lines), markup)
    return await edit_bot_message(menu, peer, "\n".join(lines), markup)


async def page_bot_token(peer: Peer, bot_id: int, menu: MessageRef, *, list_key: str = "b0") -> MessageRef:
    bot_user = await _get_bot_user(bot_id)
    if bot_user is None:
        return await edit_bot_message(menu, peer, "Bot not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    bot_row = await Bot.get_or_none(bot_id=bot_id)
    if bot_row is None:
        return await edit_bot_message(menu, peer, "Bot record not found.", ReplyInlineMarkup(rows=[_bot_back_row(list_key)]))

    token = f"{bot_id}:{bot_row.token_nonce}"
    lines = [
        f"🔑 API token — {bot_user.first_name}",
        "",
        token,
        "",
        "Use with Bot API: /bot<token>/<method>",
    ]
    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Revoke token", data=f"adm:act:revtoken:bot:{bot_id}:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to bot", data=f"adm:bot:{bot_id}:{list_key}".encode()),
        ]),
    ]
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_bot_settings(
        peer: Peer, bot_id: int, menu: MessageRef, *, list_key: str = "b0", new_message: bool = False,
) -> MessageRef:
    bot_user = await _get_bot_user(bot_id)
    if bot_user is None:
        markup = ReplyInlineMarkup(rows=[back_home_row()])
        if new_message:
            return await push_bot_message(peer, "Bot not found.", markup)
        return await edit_bot_message(menu, peer, "Bot not found.", markup)

    info = await BotInfo.get_or_none(user_id=bot_id)
    commands = list(await BotCommand.filter(bot_id=bot_id).order_by("name").limit(12))
    username = await bot_user.get_raw_username()

    display_name = bot_user.first_name
    if bot_user.last_name:
        display_name = f"{display_name} {bot_user.last_name}"

    lines = [f"⚙️ Settings — {display_name}", ""]
    lines.append(f"Name: {bot_user.first_name}")
    lines.append(f"Last name: {bot_user.last_name or '—'}")
    lines.append(f"Username: @{username}" if username else "Username: —")
    lines.append(f"About: {bot_user.about or '—'}")
    if info is None:
        lines.append("Description: —")
        lines.append("Privacy policy: —")
    else:
        lines.append(f"Description: {info.description or '—'}")
        lines.append(f"Privacy policy: {info.privacy_policy_url or '—'}")
        lines.append(f"BotInfo version: {info.version}")

    lines.append("")
    lines.append(f"Commands ({len(commands)}):")
    if not commands:
        lines.append("—")
    else:
        for cmd in commands:
            lines.append(f"/{cmd.name} — {cmd.description[:60]}")

    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="✏️ Name", data=f"adm:bot:edit:name:{bot_id}:{list_key}".encode()),
            KeyboardButtonCallback(text="✏️ Last name", data=f"adm:bot:edit:lastname:{bot_id}:{list_key}".encode()),
        ]),
    ]
    if not bot_user.system:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="✏️ Username", data=f"adm:bot:edit:username:{bot_id}:{list_key}".encode()),
        ]))
    rows.extend([
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="✏️ About", data=f"adm:bot:edit:about:{bot_id}:{list_key}".encode()),
            KeyboardButtonCallback(text="✏️ Description", data=f"adm:bot:edit:desc:{bot_id}:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="✏️ Privacy URL", data=f"adm:bot:edit:privacy:{bot_id}:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to bot", data=f"adm:bot:{bot_id}:{list_key}".encode()),
        ]),
    ])
    markup = ReplyInlineMarkup(rows=rows)
    if new_message:
        return await push_bot_message(peer, "\n".join(lines), markup)
    return await edit_bot_message(menu, peer, "\n".join(lines), markup)


async def page_channel(
        peer: Peer, channel_id: int, menu: MessageRef, *, list_key: str = "c0", new_message: bool = False,
) -> MessageRef:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        markup = ReplyInlineMarkup(rows=[back_home_row()])
        if new_message:
            return await push_bot_message(peer, "Channel not found.", markup)
        return await edit_bot_message(menu, peer, "Channel not found.", markup)

    kind = "channel" if channel.channel else "supergroup"
    username_row = await Username.get_or_none(channel_id=channel.id)
    creator = await User.get_or_none(id=channel.creator_id)

    lines = [
        f"📢 [{kind}] {channel.name}",
        f"ID: {channel.make_id()}",
        f"DB id: {channel.id}",
        f"Username: @{username_row.username}" if username_row else "Username: —",
        f"Members: {channel.participants_count}",
        f"Admins: {channel.admins_count}",
        f"Verified: {'yes' if channel.verified else 'no'}",
        f"Creator: {creator.first_name if creator else '—'} (id {channel.creator_id})",
    ]
    if channel.description:
        lines.append(f"About: {channel.description[:120]}")

    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="👥 Members", data=f"adm:ch:mem:{channel_id}:0:{list_key}".encode()),
            KeyboardButtonCallback(text="🛡 Admins", data=f"adm:ch:adm:{channel_id}:0:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="Remove ✓" if channel.verified else "Grant ✓",
                data=(
                    f"adm:act:uv:ch:{channel_id}:{list_key}".encode()
                    if channel.verified else f"adm:act:v:ch:{channel_id}:{list_key}".encode()
                ),
            ),
            KeyboardButtonCallback(text="Delete", data=f"adm:act:delch:{channel_id}:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Transfer owner", data=f"adm:ch:own:{channel_id}:{list_key}".encode()),
        ]),
    ]
    if new_message:
        rows.append(hide_row())
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Channels", data=f"adm:channels:{list_key[1:]}".encode()),
            KeyboardButtonCallback(text="« Main menu", data=HOME),
        ]))
    markup = ReplyInlineMarkup(rows=rows)
    if new_message:
        return await push_bot_message(peer, "\n".join(lines), markup)
    return await edit_bot_message(menu, peer, "\n".join(lines), markup)


async def page_group(
        peer: Peer, chat_id: int, menu: MessageRef, *, list_key: str = "g0", new_message: bool = False,
) -> MessageRef:
    chat = await Chat.get_or_none(id=chat_id, deleted=False, migrated=False)
    if chat is None:
        markup = ReplyInlineMarkup(rows=[back_home_row()])
        if new_message:
            return await push_bot_message(peer, "Group not found.", markup)
        return await edit_bot_message(menu, peer, "Group not found.", markup)

    creator = await User.get_or_none(id=chat.creator_id)
    lines = [
        f"💬 {chat.name}",
        f"ID: {chat.make_id()}",
        f"Members: {chat.participants_count}",
        f"Verified: {'yes' if chat.verified else 'no'}",
        f"Creator: {creator.first_name if creator else '—'} (id {chat.creator_id})",
    ]
    if chat.description:
        lines.append(f"About: {chat.description[:120]}")

    rows = [
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="👥 Members", data=f"adm:gr:mem:{chat_id}:0:{list_key}".encode()),
            KeyboardButtonCallback(text="🛡 Admins", data=f"adm:gr:adm:{chat_id}:0:{list_key}".encode()),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text="Remove ✓" if chat.verified else "Grant ✓",
                data=(
                    f"adm:act:uv:g:{chat_id}:{list_key}".encode()
                    if chat.verified else f"adm:act:v:g:{chat_id}:{list_key}".encode()
                ),
            ),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Transfer owner", data=f"adm:gr:own:{chat_id}:{list_key}".encode()),
        ]),
    ]
    if new_message:
        rows.append(hide_row())
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Groups", data=f"adm:groups:{list_key[1:]}".encode()),
            KeyboardButtonCallback(text="« Main menu", data=HOME),
        ]))
    markup = ReplyInlineMarkup(rows=rows)
    if new_message:
        return await push_bot_message(peer, "\n".join(lines), markup)
    return await edit_bot_message(menu, peer, "\n".join(lines), markup)


async def _member_lines(participants: list[ChatParticipant], users_map: dict[int, User]) -> list[str]:
    lines = []
    for p in participants:
        u = users_map.get(p.user_id)
        name = u.first_name if u else str(p.user_id)
        role = "creator" if p.admin_rights else ("admin" if p.is_admin else "member")
        if p.left:
            role = "left"
        lines.append(f"• {name} (id {p.user_id}) — {role}")
    return lines


async def _admin_participants(participants: list[ChatParticipant], creator_id: int) -> list[ChatParticipant]:
    return [p for p in participants if p.user_id == creator_id or p.is_admin]


async def page_channel_admins(
        peer: Peer, channel_id: int, page: int, menu: MessageRef, *, list_key: str = "c0",
) -> MessageRef:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return await edit_bot_message(menu, peer, "Not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    all_participants = list(
        await ChatParticipant.filter(channel_id=channel_id, left=False).order_by("-admin_rights", "user_id"),
    )
    admins = await _admin_participants(all_participants, channel.creator_id)
    total = len(admins)
    chunk = admins[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    user_ids = [p.user_id for p in chunk]
    users_map = {u.id: u for u in await User.filter(id__in=user_ids)} if user_ids else {}

    lines = [f"🛡 Admins of {channel.name} ({total})", ""]
    lines.extend(await _member_lines(chunk, users_map))

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows: list[KeyboardButtonRow] = []
    for p in chunk:
        name = users_map[p.user_id].first_name if p.user_id in users_map else str(p.user_id)
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text=f"Open {name[:24]}", data=user_open_link(p.user_id, list_key)),
        ]))

    nav: list[KeyboardButtonCallback] = []
    if page > 0:
        nav.append(KeyboardButtonCallback(text="«", data=f"adm:ch:adm:{channel_id}:{page - 1}:{list_key}".encode()))
    if page + 1 < total_pages:
        nav.append(KeyboardButtonCallback(text="»", data=f"adm:ch:adm:{channel_id}:{page + 1}:{list_key}".encode()))
    if nav:
        rows.append(KeyboardButtonRow(buttons=nav))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Channel", data=f"adm:ch:{channel_id}:{list_key}".encode()),
    ]))
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_group_admins(
        peer: Peer, chat_id: int, page: int, menu: MessageRef, *, list_key: str = "g0",
) -> MessageRef:
    chat = await Chat.get_or_none(id=chat_id, deleted=False)
    if chat is None:
        return await edit_bot_message(menu, peer, "Not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    all_participants = list(
        await ChatParticipant.filter(chat_id=chat_id).order_by("-admin_rights", "user_id"),
    )
    admins = await _admin_participants(all_participants, chat.creator_id)
    total = len(admins)
    chunk = admins[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    user_ids = [p.user_id for p in chunk]
    users_map = {u.id: u for u in await User.filter(id__in=user_ids)} if user_ids else {}

    lines = [f"🛡 Admins of {chat.name} ({total})", ""]
    lines.extend(await _member_lines(chunk, users_map))

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows: list[KeyboardButtonRow] = []
    for p in chunk:
        name = users_map[p.user_id].first_name if p.user_id in users_map else str(p.user_id)
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text=f"Open {name[:24]}", data=user_open_link(p.user_id, list_key)),
        ]))

    nav: list[KeyboardButtonCallback] = []
    if page > 0:
        nav.append(KeyboardButtonCallback(text="«", data=f"adm:gr:adm:{chat_id}:{page - 1}:{list_key}".encode()))
    if page + 1 < total_pages:
        nav.append(KeyboardButtonCallback(text="»", data=f"adm:gr:adm:{chat_id}:{page + 1}:{list_key}".encode()))
    if nav:
        rows.append(KeyboardButtonRow(buttons=nav))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Group", data=f"adm:gr:{chat_id}:{list_key}".encode()),
    ]))
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_channel_members(
        peer: Peer, channel_id: int, page: int, menu: MessageRef, *, list_key: str = "c0",
) -> MessageRef:
    channel = await Channel.get_or_none(id=channel_id, deleted=False)
    if channel is None:
        return await edit_bot_message(menu, peer, "Not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    total = await ChatParticipant.filter(channel_id=channel_id, left=False).count()
    participants = list(
        await ChatParticipant.filter(channel_id=channel_id, left=False).order_by("-admin_rights", "user_id")
        .offset(page * PAGE_SIZE).limit(PAGE_SIZE)
    )
    user_ids = [p.user_id for p in participants]
    users_map = {u.id: u for u in await User.filter(id__in=user_ids)} if user_ids else {}

    lines = [f"👥 Members of {channel.name} ({total})", ""]
    lines.extend(await _member_lines(participants, users_map))

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows: list[KeyboardButtonRow] = []
    for p in participants:
        if p.user_id != channel.creator_id:
            rows.append(KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(
                    text=f"Kick {users_map[p.user_id].first_name[:20] if p.user_id in users_map else p.user_id}",
                    data=f"adm:act:kickch:{channel_id}:{p.user_id}:{list_key}".encode(),
                ),
                KeyboardButtonCallback(
                    text="Make admin",
                    data=f"adm:act:admch:{channel_id}:{p.user_id}:{list_key}".encode(),
                ),
            ]))

    nav: list[KeyboardButtonCallback] = []
    if page > 0:
        nav.append(KeyboardButtonCallback(text="«", data=f"adm:ch:mem:{channel_id}:{page - 1}:{list_key}".encode()))
    if page + 1 < total_pages:
        nav.append(KeyboardButtonCallback(text="»", data=f"adm:ch:mem:{channel_id}:{page + 1}:{list_key}".encode()))
    if nav:
        rows.append(KeyboardButtonRow(buttons=nav))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Channel", data=f"adm:ch:{channel_id}:{list_key}".encode()),
    ]))
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def page_group_members(
        peer: Peer, chat_id: int, page: int, menu: MessageRef, *, list_key: str = "g0",
) -> MessageRef:
    chat = await Chat.get_or_none(id=chat_id, deleted=False)
    if chat is None:
        return await edit_bot_message(menu, peer, "Not found.", ReplyInlineMarkup(rows=[back_home_row()]))

    total = await ChatParticipant.filter(chat_id=chat_id).count()
    participants = list(
        await ChatParticipant.filter(chat_id=chat_id).order_by("-admin_rights", "user_id")
        .offset(page * PAGE_SIZE).limit(PAGE_SIZE)
    )
    user_ids = [p.user_id for p in participants]
    users_map = {u.id: u for u in await User.filter(id__in=user_ids)} if user_ids else {}

    lines = [f"👥 Members of {chat.name} ({total})", ""]
    lines.extend(await _member_lines(participants, users_map))

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows: list[KeyboardButtonRow] = []
    for p in participants:
        if p.user_id != chat.creator_id:
            rows.append(KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(
                    text=f"Kick {(users_map[p.user_id].first_name if p.user_id in users_map else p.user_id)}"[:24],
                    data=f"adm:act:kickgr:{chat_id}:{p.user_id}:{list_key}".encode(),
                ),
                KeyboardButtonCallback(
                    text="Make admin",
                    data=f"adm:act:admgr:{chat_id}:{p.user_id}:{list_key}".encode(),
                ),
            ]))

    nav: list[KeyboardButtonCallback] = []
    if page > 0:
        nav.append(KeyboardButtonCallback(text="«", data=f"adm:gr:mem:{chat_id}:{page - 1}:{list_key}".encode()))
    if page + 1 < total_pages:
        nav.append(KeyboardButtonCallback(text="»", data=f"adm:gr:mem:{chat_id}:{page + 1}:{list_key}".encode()))
    if nav:
        rows.append(KeyboardButtonRow(buttons=nav))
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Group", data=f"adm:gr:{chat_id}:{list_key}".encode()),
    ]))
    return await edit_bot_message(menu, peer, "\n".join(lines), ReplyInlineMarkup(rows=rows))


async def _report_list_label(report: AdminReport) -> str:
    mark = "✓" if report.reviewed else "•"
    kind = format_peer_type(report.peer_type).split()[0]
    reason = format_report_reason(report.reason)
    return f"{mark} #{report.id} [{kind}] {reason}"[:64]


async def page_reports(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    reports = list(await AdminReport.filter().order_by("-id"))
    total = len(reports)
    pending = sum(1 for r in reports if not r.reviewed)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
    page = max(0, min(page, total_pages - 1))
    chunk = reports[page * PAGE_SIZE:(page + 1) * PAGE_SIZE] if total else []

    items = []
    for r in chunk:
        items.append((await _report_list_label(r), f"adm:report:{r.id}:r{page}".encode()))

    text = f"📩 Reports ({total}, {pending} pending). Tap for details:"
    if total == 0:
        text = "📩 No reports yet."
    return await edit_bot_message(
        menu, peer, text, list_keyboard(
            items=items, page=page, total_pages=total_pages, page_prefix=b"adm:reports",
        ),
    )


async def page_report(
        peer: Peer, report_id: int, menu: MessageRef, *, list_key: str = "r0", overlay: bool = False,
) -> MessageRef:
    report = await AdminReport.get_or_none(id=report_id)
    if report is None:
        markup = ReplyInlineMarkup(rows=[back_home_row()])
        if overlay:
            return await push_bot_message(peer, "Report not found.", markup)
        return await edit_bot_message(menu, peer, "Report not found.", markup)

    lines = await build_report_detail_lines(report)
    ctx = await get_report_context(report)
    rows: list[KeyboardButtonRow] = []

    if report.peer_type is AdminReportPeerType.USER:
        if ctx.target_is_bot:
            rows.append(KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text="🤖 Open bot", data=bot_open_link(report.peer_id, list_key)),
                KeyboardButtonCallback(
                    text="🗑 Ban bot",
                    data=f"adm:act:banbotrep:{report_id}:{report.peer_id}:{list_key}".encode(),
                ),
            ]))
        else:
            rows.append(KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text="👤 Open user", data=user_open_link(report.peer_id, list_key)),
                KeyboardButtonCallback(
                    text="🚫 Spam block",
                    data=f"adm:act:spamrep:{report_id}:{report.peer_id}:{list_key}".encode(),
                ),
                KeyboardButtonCallback(
                    text="🗑 Ban user",
                    data=f"adm:act:banrep:{report_id}:{report.peer_id}:{list_key}".encode(),
                ),
            ]))
        if ctx.author_id is not None and ctx.author_id != report.peer_id:
            author_row = []
            if ctx.author_is_bot:
                author_row.append(KeyboardButtonCallback(
                    text="🤖 Open author bot", data=bot_open_link(ctx.author_id, list_key),
                ))
                author_row.append(KeyboardButtonCallback(
                    text="🗑 Ban author bot",
                    data=f"adm:act:banbotrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                ))
            else:
                author_row.append(KeyboardButtonCallback(
                    text="👤 Open author", data=user_open_link(ctx.author_id, list_key),
                ))
                author_row.append(KeyboardButtonCallback(
                    text="🚫 Spam author",
                    data=f"adm:act:spamauthrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                ))
                author_row.append(KeyboardButtonCallback(
                    text="🗑 Ban author",
                    data=f"adm:act:banrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                ))
            rows.append(KeyboardButtonRow(buttons=author_row))
    elif report.peer_type is AdminReportPeerType.CHANNEL:
        channel_row = [
            KeyboardButtonCallback(
                text="📢 Open channel",
                data=f"adm:ch:open:{report.peer_id}:{list_key}".encode(),
            ),
        ]
        if ctx.author_id is not None:
            if ctx.author_is_bot:
                channel_row.append(KeyboardButtonCallback(
                    text="🤖 Open author bot", data=bot_open_link(ctx.author_id, list_key),
                ))
            else:
                channel_row.append(KeyboardButtonCallback(
                    text="👤 Open author", data=user_open_link(ctx.author_id, list_key),
                ))
        rows.append(KeyboardButtonRow(buttons=channel_row))
        if ctx.author_id is not None:
            if ctx.author_is_bot:
                rows.append(KeyboardButtonRow(buttons=[
                    KeyboardButtonCallback(
                        text="🗑 Ban bot",
                        data=f"adm:act:banbotrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                ]))
            else:
                rows.append(KeyboardButtonRow(buttons=[
                    KeyboardButtonCallback(
                        text="🗑 Ban author",
                        data=f"adm:act:banrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                    KeyboardButtonCallback(
                        text="🚫 Spam block author",
                        data=f"adm:act:spamauthrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                ]))
    elif report.peer_type is AdminReportPeerType.CHAT:
        group_row = [
            KeyboardButtonCallback(
                text="💬 Open group",
                data=f"adm:gr:open:{report.peer_id}:{list_key}".encode(),
            ),
        ]
        if ctx.author_id is not None:
            if ctx.author_is_bot:
                group_row.append(KeyboardButtonCallback(
                    text="🤖 Open author bot", data=bot_open_link(ctx.author_id, list_key),
                ))
            else:
                group_row.append(KeyboardButtonCallback(
                    text="👤 Open author", data=user_open_link(ctx.author_id, list_key),
                ))
        rows.append(KeyboardButtonRow(buttons=group_row))
        if ctx.author_id is not None:
            if ctx.author_is_bot:
                rows.append(KeyboardButtonRow(buttons=[
                    KeyboardButtonCallback(
                        text="🗑 Ban bot",
                        data=f"adm:act:banbotrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                ]))
            else:
                rows.append(KeyboardButtonRow(buttons=[
                    KeyboardButtonCallback(
                        text="🗑 Ban author",
                        data=f"adm:act:banrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                    KeyboardButtonCallback(
                        text="🚫 Spam block author",
                        data=f"adm:act:spamauthrep:{report_id}:{ctx.author_id}:{list_key}".encode(),
                    ),
                ]))

    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="👤 Open reporter", data=user_open_link(report.reporter_id, list_key)),
    ]))
    if not report.reviewed:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Mark reviewed", data=f"adm:act:revrep:{report_id}:{list_key}".encode()),
        ]))
    if overlay:
        rows.append(hide_row())
    else:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Reports", data=f"adm:reports:{list_key[1:]}".encode()),
            KeyboardButtonCallback(text="« Main menu", data=HOME),
        ]))
    markup = ReplyInlineMarkup(rows=rows)
    if overlay:
        return await push_bot_message(peer, "\n".join(lines), markup)
    return await edit_bot_message(menu, peer, "\n".join(lines), markup)