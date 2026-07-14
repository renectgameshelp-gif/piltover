from __future__ import annotations

from piltover.db.models import MessageRef, Peer
from piltover.tl import KeyboardButtonCallback, KeyboardButtonRow, ReplyInlineMarkup

PAGE_SIZE = 8


def _badge(verified: bool) -> str:
    return " ✓" if verified else ""


def main_menu_keyboard() -> ReplyInlineMarkup:
    return ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="My account", data=b"page:self"),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="My bots", data=b"page:bots:0"),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="My groups & channels", data=b"page:chats:0"),
        ]),
    ])


def self_keyboard(*, verified: bool) -> ReplyInlineMarkup:
    if verified:
        action = KeyboardButtonCallback(text="Remove checkmark", data=b"act:uv:u:0")
    else:
        action = KeyboardButtonCallback(text="Get checkmark", data=b"act:v:u:0")
    return ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[action]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="« Back", data=b"page:home"),
        ]),
    ])


def list_keyboard(
        *,
        items: list[tuple[str, bytes]],
        page: int,
        total_pages: int,
        page_prefix: bytes,
) -> ReplyInlineMarkup:
    rows: list[KeyboardButtonRow] = []
    for label, data in items:
        rows.append(KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text=label, data=data),
        ]))

    nav: list[KeyboardButtonCallback] = []
    if page > 0:
        nav.append(KeyboardButtonCallback(text="« Prev", data=f"{page_prefix.decode()}:{page - 1}".encode()))
    if page + 1 < total_pages:
        nav.append(KeyboardButtonCallback(text="Next »", data=f"{page_prefix.decode()}:{page + 1}".encode()))
    if nav:
        rows.append(KeyboardButtonRow(buttons=nav))

    rows.append(KeyboardButtonRow(buttons=[
        KeyboardButtonCallback(text="« Back", data=b"page:home"),
    ]))
    return ReplyInlineMarkup(rows=rows)


def entity_label(name: str, *, verified: bool, suffix: str = "") -> str:
    text = f"{name}{suffix}{_badge(verified)}"
    if len(text) > 64:
        text = text[:61] + "..."
    return text


async def send_bot_message(
        peer: Peer, text: str, keyboard: ReplyInlineMarkup | None = None,
) -> MessageRef:
    messages = await MessageRef.create_for_peer(
        peer, peer.user_id, opposite=False,
        message=text, reply_markup=keyboard.write() if keyboard else None,
    )
    return messages[peer]