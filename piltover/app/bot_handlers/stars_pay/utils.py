from piltover.app.utils.stars_manager import STARS_CURRENCY, _pack_invoice_static, make_invoice_buy_markup
from piltover.db.enums import MediaType
from piltover.db.models import Peer, MessageRef, MessageMedia
from piltover.tl import KeyboardButtonRow, KeyboardButtonCallback, ReplyInlineMarkup, MessageMediaInvoice

INVOICE_AMOUNTS = (1, 5, 10, 25)


def get_pay_keyboard() -> ReplyInlineMarkup:
    rows: list[KeyboardButtonRow] = []
    for idx, amount in enumerate(INVOICE_AMOUNTS):
        if idx % 2 == 0:
            rows.append(KeyboardButtonRow(buttons=[]))
        rows[-1].buttons.append(KeyboardButtonCallback(
            text=f"Pay {amount} ⭐",
            data=f"pay/{amount}".encode("latin1"),
        ))
    return ReplyInlineMarkup(rows=rows)


async def send_bot_message(
        peer: Peer, text: str, keyboard: ReplyInlineMarkup | None = None,
) -> MessageRef:
    messages = await MessageRef.create_for_peer(
        peer, peer.user, opposite=False,
        message=text, reply_markup=keyboard.write() if keyboard else None,
    )
    return messages[peer]


async def send_stars_invoice(peer: Peer, amount: int) -> MessageRef:
    payload = f"stars-pay/{amount}".encode("utf-8")
    invoice_tl = MessageMediaInvoice(
        title=f"{amount} Stars",
        description=f"Test payment of {amount} Telegram Stars",
        currency=STARS_CURRENCY,
        total_amount=amount,
        start_param="",
    )
    media = await MessageMedia.create(
        type=MediaType.INVOICE,
        static_data=_pack_invoice_static(invoice_tl, payload),
    )
    buy_markup = make_invoice_buy_markup(STARS_CURRENCY, amount)
    messages = await MessageRef.create_for_peer(
        peer, peer.user, opposite=False,
        media=media, reply_markup=buy_markup.write(),
    )
    return messages[peer]