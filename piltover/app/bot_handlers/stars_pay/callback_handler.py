import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.stars_pay.utils import INVOICE_AMOUNTS, send_stars_invoice
from piltover.db.models import Peer, MessageRef
from piltover.tl.types.messages import BotCallbackAnswer


async def stars_pay_callback_query_handler(
        peer: Peer, _message: MessageRef, data: bytes,
) -> BotCallbackAnswer | None:
    if not data.startswith(b"pay/"):
        return None

    try:
        amount = int(data[4:])
    except ValueError:
        return None

    if amount not in INVOICE_AMOUNTS:
        return None

    invoice_message = await send_stars_invoice(peer, amount)
    await upd.send_message(None, {peer: invoice_message}, False)

    return BotCallbackAnswer(
        message=f"Invoice for {amount} stars sent!",
        cache_time=0,
    )