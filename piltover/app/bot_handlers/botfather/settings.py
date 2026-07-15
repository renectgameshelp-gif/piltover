from __future__ import annotations

from dataclasses import dataclass

from tortoise.expressions import F
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.utils import apply_message_edit
from piltover.db.enums import ChatAdminRights
from piltover.db.models import Bot, BotInfo, MessageRef, Peer, User
from piltover.tl import KeyboardButtonCallback, KeyboardButtonRow, ReplyInlineMarkup
from piltover.tl.types.messages import BotCallbackAnswer

_SETTINGS_UPDATED = BotCallbackAnswer(message="Settings updated!", cache_time=0)
_EMPTY_CLICK = BotCallbackAnswer(cache_time=0)

_ADMIN_RIGHT_BUTTONS: list[tuple[str, str, ChatAdminRights]] = [
    ("Change group name, photo, etc.", "ci", ChatAdminRights.CHANGE_INFO),
    ("Restrict, ban or unban members", "bu", ChatAdminRights.BAN_USERS),
    ("Pin messages", "pim", ChatAdminRights.PIN_MESSAGES),
    ("Manage voice chats", "mvc", ChatAdminRights.MANAGE_CALL),
    ("Manage Topics", "mt", ChatAdminRights.MANAGE_TOPICS),
    ("Edit stories", "es", ChatAdminRights.EDIT_STORIES),
    ("Delete messages", "dm", ChatAdminRights.DELETE_MESSAGES),
    ("Invite new users", "iu", ChatAdminRights.INVITE_USERS),
    ("Add new administrators", "aa", ChatAdminRights.ADD_ADMINS),
    ("Promote anonymous admins", "pa", ChatAdminRights.ANONYMOUS),
    ("Post stories", "ps", ChatAdminRights.POST_STORIES),
    ("Delete stories", "ds", ChatAdminRights.DELETE_STORIES),
    ("Manage chat", "o", ChatAdminRights.OTHER),
]

_CHANNEL_ADMIN_RIGHT_BUTTONS: list[tuple[str, str, ChatAdminRights]] = [
    ("Change channel info", "ci", ChatAdminRights.CHANGE_INFO),
    ("Post messages", "pm", ChatAdminRights.POST_MESSAGES),
    ("Edit messages", "em", ChatAdminRights.EDIT_MESSAGES),
    ("Delete messages", "dm", ChatAdminRights.DELETE_MESSAGES),
    ("Restrict members", "bu", ChatAdminRights.BAN_USERS),
    ("Invite users", "iu", ChatAdminRights.INVITE_USERS),
    ("Pin messages", "pim", ChatAdminRights.PIN_MESSAGES),
    ("Manage video chats", "mvc", ChatAdminRights.MANAGE_CALL),
    ("Add administrators", "aa", ChatAdminRights.ADD_ADMINS),
    ("Post stories", "ps", ChatAdminRights.POST_STORIES),
    ("Edit stories", "es", ChatAdminRights.EDIT_STORIES),
    ("Delete stories", "ds", ChatAdminRights.DELETE_STORIES),
]


@dataclass(frozen=True)
class _BotRef:
    bot_id: int
    first_name: str
    username: str


async def _get_owned_bot(owner_id: int, bot_id: int) -> _BotRef | None:
    row = await User.get_or_none(
        id=bot_id, bot_bot__owner_id=owner_id,
    ).select_related("username").values_list("first_name", "username__username")
    if row is None:
        return None
    first_name, username = row
    if not username:
        return None
    return _BotRef(bot_id=bot_id, first_name=first_name, username=username)


async def _save_message(peer: Peer, message: MessageRef, *, text: str, keyboard: ReplyInlineMarkup) -> None:
    apply_message_edit(message.content, message=text, entities=None, reply_markup=keyboard)
    async with in_transaction():
        await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
    await upd.edit_message(peer.owner_id, {peer: message})


def _bot_mention(bot: _BotRef) -> str:
    return f"{bot.first_name} @{bot.username}"


def _right_button_text(label: str, rights: int, flag: ChatAdminRights) -> str:
    if rights & flag:
        return f"✅ {label}"
    return label


def _admin_rights_rows(
        bot_id: int, rights: int, buttons: list[tuple[str, str, ChatAdminRights]], *, prefix: str,
) -> list[KeyboardButtonRow]:
    rows: list[KeyboardButtonRow] = []
    left_column = buttons[:6]
    right_column = buttons[6:12]
    extra = buttons[12:]

    for left, right in zip(left_column, right_column):
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text=_right_button_text(left[0], rights, left[2]),
                data=f"bset/{prefix}t/{bot_id}/{left[1]}".encode("latin1"),
            ),
            KeyboardButtonCallback(
                text=_right_button_text(right[0], rights, right[2]),
                data=f"bset/{prefix}t/{bot_id}/{right[1]}".encode("latin1"),
            ),
        ]))

    for label, key, flag in extra:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(
                text=_right_button_text(label, rights, flag),
                data=f"bset/{prefix}t/{bot_id}/{key}".encode("latin1"),
            ),
        ]))

    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Back to Settings", data=f"bset/{bot_id}".encode("latin1")),
    ]))
    return rows


async def _show_main_menu(peer: Peer, message: MessageRef, bot: _BotRef) -> BotCallbackAnswer:
    text = f"Settings for @{bot.username}."
    keyboard = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Inline Mode", data=f"bset/i/{bot.bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Allow Groups?", data=f"bset/g/{bot.bot_id}".encode("latin1")),
            KeyboardButtonCallback(text="Group Privacy", data=f"bset/p/{bot.bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Group Admin Rights", data=f"bset/ga/{bot.bot_id}".encode("latin1")),
            KeyboardButtonCallback(text="Channel Admin Rights", data=f"bset/ca/{bot.bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Payments", data=f"bset/x/{bot.bot_id}/pay".encode("latin1")),
            KeyboardButtonCallback(text="Domain", data=f"bset/x/{bot.bot_id}/dom".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Menu Button", data=f"bset/x/{bot.bot_id}/menu".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Configure Mini App", data=f"bset/x/{bot.bot_id}/mini".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Paid Broadcast", data=f"bset/x/{bot.bot_id}/paid".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to Bot", data=f"bots/{bot.bot_id}".encode("latin1")),
        ]),
    ])
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


async def _show_inline_mode(peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo) -> BotCallbackAnswer:
    if info.inline_mode:
        text = (
            f"Inline mode is currently enabled for {_bot_mention(bot)}.\n\n"
            f"Disabling inline mode will forbid users to use @{bot.username} in inline mode."
        )
        toggle = KeyboardButtonCallback(text="Turn off", data=f"bset/i0/{bot.bot_id}".encode("latin1"))
    else:
        text = f"Inline mode is currently disabled for {_bot_mention(bot)}."
        toggle = KeyboardButtonCallback(text="Turn on", data=f"bset/i1/{bot.bot_id}".encode("latin1"))

    keyboard = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[toggle]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to Settings", data=f"bset/{bot.bot_id}".encode("latin1")),
        ]),
    ])
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


async def _show_groups(peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo) -> BotCallbackAnswer:
    if info.can_join_groups:
        text = (
            f"Groups are currently enabled for bot {_bot_mention(bot)}.\n\n"
            f"Disabling groups will forbid users to add {bot.first_name} to groups."
        )
        toggle = KeyboardButtonCallback(text="Turn groups off", data=f"bset/g0/{bot.bot_id}".encode("latin1"))
    else:
        text = (
            f"Groups are currently disabled for bot {_bot_mention(bot)}.\n\n"
            f"Enabling groups will allow users to add {bot.first_name} to groups."
        )
        toggle = KeyboardButtonCallback(text="Turn groups on", data=f"bset/g1/{bot.bot_id}".encode("latin1"))

    keyboard = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[toggle]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to Settings", data=f"bset/{bot.bot_id}".encode("latin1")),
        ]),
    ])
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


async def _show_group_privacy(peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo) -> BotCallbackAnswer:
    if info.group_privacy:
        text = (
            f"Privacy mode is enabled for bot {_bot_mention(bot)}.\n\n"
            "When enabled, the bot only receives messages that start with a / command, "
            "mention the bot, or are replies to the bot's messages."
        )
        toggle = KeyboardButtonCallback(text="Turn privacy off", data=f"bset/p0/{bot.bot_id}".encode("latin1"))
    else:
        text = (
            f"Privacy mode is disabled for bot {_bot_mention(bot)}.\n\n"
            "When disabled, the bot receives all messages in groups."
        )
        toggle = KeyboardButtonCallback(text="Turn privacy on", data=f"bset/p1/{bot.bot_id}".encode("latin1"))

    keyboard = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[toggle]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back to Settings", data=f"bset/{bot.bot_id}".encode("latin1")),
        ]),
    ])
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


async def _show_group_admin_rights(peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo) -> BotCallbackAnswer:
    text = (
        f"You can choose which rights the bot {_bot_mention(bot)} will request by default "
        "when added as a group admin.\n\n"
        "If the bot doesn't support managing groups, please remove all checks."
    )
    keyboard = ReplyInlineMarkup(rows=_admin_rights_rows(
        bot.bot_id, info.group_admin_rights, _ADMIN_RIGHT_BUTTONS, prefix="ga",
    ))
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


async def _show_channel_admin_rights(peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo) -> BotCallbackAnswer:
    text = (
        f"You can choose which rights the bot {_bot_mention(bot)} will request by default "
        "when added as a channel admin.\n\n"
        "If the bot doesn't support managing channels, please remove all checks."
    )
    rows = _admin_rights_rows(bot.bot_id, info.channel_admin_rights, _CHANNEL_ADMIN_RIGHT_BUTTONS, prefix="ca")
    keyboard = ReplyInlineMarkup(rows=rows)
    await _save_message(peer, message, text=text, keyboard=keyboard)
    return _EMPTY_CLICK


def _right_from_key(key: str, buttons: list[tuple[str, str, ChatAdminRights]]) -> ChatAdminRights | None:
    for _, button_key, flag in buttons:
        if button_key == key:
            return flag
    return None


async def _toggle_admin_right(
        peer: Peer, message: MessageRef, bot: _BotRef, info: BotInfo, *,
        field: str, key: str, buttons: list[tuple[str, str, ChatAdminRights]], show_page,
) -> BotCallbackAnswer:
    flag = _right_from_key(key, buttons)
    if flag is None:
        return _EMPTY_CLICK

    current = getattr(info, field)
    new_rights = current & ~flag if current & flag else current | flag
    await BotInfo.filter(id=info.id).update(**{field: new_rights, "version": F("version") + 1})
    await info.refresh_from_db(fields=[field, "version"])

    await show_page(peer, message, bot, info)
    return _SETTINGS_UPDATED


async def handle_bot_settings_callback(peer: Peer, message: MessageRef, data: bytes) -> BotCallbackAnswer | None:
    text = data.decode("latin1")

    if text.startswith("bots-settings/"):
        try:
            bot_id = int(text[14:])
        except ValueError:
            return None
        bot = await _get_owned_bot(peer.owner_id, bot_id)
        if bot is None:
            return None
        return await _show_main_menu(peer, message, bot)

    if not text.startswith("bset/"):
        return None

    parts = text.split("/")
    if len(parts) < 2:
        return None

    if parts[1] == "x" and len(parts) == 4:
        try:
            bot_id = int(parts[2])
        except ValueError:
            return None
        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None
        return _EMPTY_CLICK

    if parts[1] in ("gat", "cat") and len(parts) == 4:
        try:
            bot_id = int(parts[2])
        except ValueError:
            return None
        bot = await _get_owned_bot(peer.owner_id, bot_id)
        if bot is None:
            return None
        info = await BotInfo.get_or_create_for_bot(bot_id)
        buttons = _ADMIN_RIGHT_BUTTONS if parts[1] == "gat" else _CHANNEL_ADMIN_RIGHT_BUTTONS
        field = "group_admin_rights" if parts[1] == "gat" else "channel_admin_rights"
        show_page = _show_group_admin_rights if parts[1] == "gat" else _show_channel_admin_rights
        return await _toggle_admin_right(
            peer, message, bot, info, field=field, key=parts[3], buttons=buttons, show_page=show_page,
        )

    if len(parts) == 2:
        try:
            bot_id = int(parts[1])
        except ValueError:
            return None
        bot = await _get_owned_bot(peer.owner_id, bot_id)
        if bot is None:
            return None
        return await _show_main_menu(peer, message, bot)

    if len(parts) != 3:
        return None

    action, bot_id_str = parts[1], parts[2]
    try:
        bot_id = int(bot_id_str)
    except ValueError:
        return None

    bot = await _get_owned_bot(peer.owner_id, bot_id)
    if bot is None:
        return None

    info = await BotInfo.get_or_create_for_bot(bot_id)

    if action == "i":
        return await _show_inline_mode(peer, message, bot, info)
    if action == "g":
        return await _show_groups(peer, message, bot, info)
    if action == "p":
        return await _show_group_privacy(peer, message, bot, info)
    if action == "ga":
        return await _show_group_admin_rights(peer, message, bot, info)
    if action == "ca":
        return await _show_channel_admin_rights(peer, message, bot, info)

    if action == "i1":
        await BotInfo.filter(id=info.id).update(inline_mode=True, version=F("version") + 1)
        await info.refresh_from_db(fields=["inline_mode", "version"])
        await _show_inline_mode(peer, message, bot, info)
        return _SETTINGS_UPDATED
    if action == "i0":
        await BotInfo.filter(id=info.id).update(inline_mode=False, version=F("version") + 1)
        await info.refresh_from_db(fields=["inline_mode", "version"])
        await _show_inline_mode(peer, message, bot, info)
        return _SETTINGS_UPDATED

    if action == "g1":
        await BotInfo.filter(id=info.id).update(can_join_groups=True, version=F("version") + 1)
        await info.refresh_from_db(fields=["can_join_groups", "version"])
        await _show_groups(peer, message, bot, info)
        return _SETTINGS_UPDATED
    if action == "g0":
        await BotInfo.filter(id=info.id).update(can_join_groups=False, version=F("version") + 1)
        await info.refresh_from_db(fields=["can_join_groups", "version"])
        await _show_groups(peer, message, bot, info)
        return _SETTINGS_UPDATED

    if action == "p1":
        await BotInfo.filter(id=info.id).update(group_privacy=True, version=F("version") + 1)
        await info.refresh_from_db(fields=["group_privacy", "version"])
        await _show_group_privacy(peer, message, bot, info)
        return _SETTINGS_UPDATED
    if action == "p0":
        await BotInfo.filter(id=info.id).update(group_privacy=False, version=F("version") + 1)
        await info.refresh_from_db(fields=["group_privacy", "version"])
        await _show_group_privacy(peer, message, bot, info)
        return _SETTINGS_UPDATED

    return None