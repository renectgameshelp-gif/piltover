from __future__ import annotations

import random

from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.utils import apply_message_edit
from piltover.app.utils.admin_channel_ops import admin_delete_bot
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.models import Bot, BotCommand, BotInfo, MessageRef, Peer, User
from piltover.tl import KeyboardButtonCallback, KeyboardButtonRow, ReplyInlineMarkup
from piltover.tl.types.messages import BotCallbackAnswer

_EMPTY_CLICK = BotCallbackAnswer(cache_time=0)

__text_bot_selected = FormatableTextWithEntities(
    "Here it is: {name} <u>@{username}</u>.\nWhat do you want to do with the bot?"
)


async def _get_owned_bot(owner_id: int, bot_id: int) -> tuple[str, str] | None:
    row = await User.get_or_none(
        id=bot_id, bot_bot__owner_id=owner_id, deleted=False,
    ).select_related("username").values_list("first_name", "username__username")
    if row is None:
        return None
    first_name, username = row
    if not username:
        return None
    return first_name, username


async def _save_message(peer: Peer, message: MessageRef, *, text: str, keyboard: ReplyInlineMarkup) -> None:
    apply_message_edit(message.content, message=text, entities=None, reply_markup=keyboard)
    async with in_transaction():
        await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
    await upd.edit_message(peer.owner_id, {peer: message})


def _confirm_keyboard(bot_id: int) -> ReplyInlineMarkup:
    choices = [
        KeyboardButtonCallback(text="Yes, delete the bot", data=f"bots-delete-y/{bot_id}".encode("latin1")),
        KeyboardButtonCallback(text="Nope, nevermind", data=f"bots-delete-n/{bot_id}".encode("latin1")),
        KeyboardButtonCallback(text="No", data=f"bots-delete-n/{bot_id}".encode("latin1")),
    ]
    random.shuffle(choices)
    rows = [KeyboardButtonRow(buttons=[btn]) for btn in choices]
    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Back to Bot", data=f"bots/{bot_id}".encode("latin1")),
    ]))
    return ReplyInlineMarkup(rows=rows)


async def show_owned_bot_card(peer: Peer, message: MessageRef, bot_id: int) -> BotCallbackAnswer | None:
    bot_info = await _get_owned_bot(peer.owner_id, bot_id)
    if bot_info is None:
        return None

    first_name, username = bot_info
    text, entities = __text_bot_selected.format(name=first_name, username=username)
    keyboard = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="API Token", data=f"bots-token/{bot_id}".encode("latin1")),
            KeyboardButtonCallback(text="Edit Bot", data=f"bots-edit/{bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Bot Settings", data=f"bset/{bot_id}".encode("latin1")),
            KeyboardButtonCallback(text="Payments", data=f"bots-payments/{bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Transfer Ownership", data=f"bots-transfer/{bot_id}".encode("latin1")),
            KeyboardButtonCallback(text="Delete Bot", data=f"bots-delete/{bot_id}".encode("latin1")),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="<- Back to Bot List", data=b"mybots"),
        ]),
    ])
    apply_message_edit(message.content, message=text, entities=entities, reply_markup=keyboard)
    async with in_transaction():
        await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
    await upd.edit_message(peer.owner_id, {peer: message})
    return _EMPTY_CLICK


async def owner_delete_bot(owner_id: int, bot_id: int) -> bool:
    bot_row = await Bot.get_or_none(bot_id=bot_id, owner_id=owner_id).select_related("bot")
    if bot_row is None:
        return False

    bot_user = bot_row.bot
    await BotCommand.filter(bot_id=bot_id).delete()
    await BotInfo.filter(user_id=bot_id).delete()
    await admin_delete_bot(bot_user)
    return True


async def handle_delete_bot_callback(peer: Peer, message: MessageRef, data: bytes) -> BotCallbackAnswer | None:
    text = data.decode("latin1")

    if text.startswith("bots-delete-y/"):
        try:
            bot_id = int(text[14:])
        except ValueError:
            return None

        bot_info = await _get_owned_bot(peer.owner_id, bot_id)
        if bot_info is None:
            return None

        if not await owner_delete_bot(peer.owner_id, bot_id):
            return None

        keyboard = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text="<- Back to Bot List", data=b"mybots"),
            ]),
        ])
        await _save_message(peer, message, text="Done! The bot is gone.", keyboard=keyboard)
        return _EMPTY_CLICK

    if text.startswith("bots-delete-n/"):
        try:
            bot_id = int(text[14:])
        except ValueError:
            return None
        return await show_owned_bot_card(peer, message, bot_id)

    if not text.startswith("bots-delete/"):
        return None

    try:
        bot_id = int(text[12:])
    except ValueError:
        return None

    bot_info = await _get_owned_bot(peer.owner_id, bot_id)
    if bot_info is None:
        return None

    first_name, username = bot_info
    confirm_text = f"You are about to delete your bot {first_name} @{username}. Is that correct?"
    await _save_message(peer, message, text=confirm_text, keyboard=_confirm_keyboard(bot_id))
    return _EMPTY_CLICK