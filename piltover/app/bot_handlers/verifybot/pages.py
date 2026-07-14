from __future__ import annotations

from piltover.app.bot_handlers.typetestbot.common import edit_bot_message
from piltover.app.bot_handlers.verifybot.utils import (
    PAGE_SIZE,
    entity_label,
    list_keyboard,
    main_menu_keyboard,
    self_keyboard,
)
from piltover.db.models import Bot, Channel, Chat, MessageRef, Peer, User


_START_TEXT = (
    "✅ Verification Bot\n\n"
    "Grant or remove the verified checkmark for your account, bots, "
    "and groups or channels you created."
)


async def page_home(peer: Peer, menu: MessageRef) -> MessageRef:
    return await edit_bot_message(menu, peer, _START_TEXT, main_menu_keyboard())


async def page_self(peer: Peer, menu: MessageRef) -> MessageRef:
    user = await User.get(id=peer.owner_id)
    status = "verified" if user.verified else "not verified"
    text = f"Your account is {status}."
    return await edit_bot_message(menu, peer, text, self_keyboard(verified=user.verified))


async def page_bots(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    bots = list(await Bot.filter(owner_id=peer.owner_id).select_related("bot").order_by("bot_id"))
    total = len(bots)
    if total == 0:
        text = "You have no bots."
        keyboard = list_keyboard(items=[], page=0, total_pages=1, page_prefix=b"page:bots")
        return await edit_bot_message(menu, peer, text, keyboard)

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = bots[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    items: list[tuple[str, bytes]] = []
    for entry in chunk:
        bot_user = entry.bot
        username = await bot_user.get_raw_username()
        suffix = f" (@{username})" if username else ""
        if bot_user.verified:
            data = f"act:uv:u:{bot_user.id}".encode()
        else:
            data = f"act:v:u:{bot_user.id}".encode()
        items.append((
            entity_label(bot_user.first_name, verified=bot_user.verified, suffix=suffix),
            data,
        ))

    text = f"My bots ({total}). Tap to toggle checkmark:"
    keyboard = list_keyboard(
        items=items,
        page=page,
        total_pages=total_pages,
        page_prefix=b"page:bots",
    )
    return await edit_bot_message(menu, peer, text, keyboard)


async def page_chats(peer: Peer, page: int, menu: MessageRef) -> MessageRef:
    channels = list(await Channel.filter(creator_id=peer.owner_id, deleted=False).order_by("id"))
    chats = list(await Chat.filter(creator_id=peer.owner_id, deleted=False, migrated=False).order_by("id"))

    entries: list[tuple[str, bool, bytes]] = []
    for channel in channels:
        kind = "channel" if channel.channel else "group"
        if channel.verified:
            data = f"act:uv:ch:{channel.id}".encode()
        else:
            data = f"act:v:ch:{channel.id}".encode()
        entries.append((f"[{kind}] {channel.name}", channel.verified, data))

    for chat in chats:
        if chat.verified:
            data = f"act:uv:g:{chat.id}".encode()
        else:
            data = f"act:v:g:{chat.id}".encode()
        entries.append((f"[group] {chat.name}", chat.verified, data))

    total = len(entries)
    if total == 0:
        text = "You have no groups or channels."
        keyboard = list_keyboard(items=[], page=0, total_pages=1, page_prefix=b"page:chats")
        return await edit_bot_message(menu, peer, text, keyboard)

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = entries[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    items = [
        (entity_label(name, verified=verified), data)
        for name, verified, data in chunk
    ]

    text = f"My groups & channels ({total}). Tap to toggle checkmark:"
    keyboard = list_keyboard(
        items=items,
        page=page,
        total_pages=total_pages,
        page_prefix=b"page:chats",
    )
    return await edit_bot_message(menu, peer, text, keyboard)