from types import NoneType

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stars_pay.utils import (
    INVOICE_AMOUNTS, get_pay_keyboard, send_bot_message, send_stars_invoice,
)
from piltover.db.models import Peer, MessageRef

_START_TEXT = (
    "💫 Stars Pay Test Bot\n\n"
    "Choose an amount below to receive a Stars invoice, "
    "or use /invoice <amount> (1, 5, 10, 25)."
)


class StarsPayBotInteractionHandler(BotInteractionHandler[NoneType, NoneType]):
    def __init__(self) -> None:
        super().__init__(None)
        self.command("start").set_send_message_func(send_bot_message).do(self._start).register()
        self.command("invoice").set_send_message_func(send_bot_message).do(self._invoice).register()

    @staticmethod
    async def _start(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        return await send_bot_message(peer, _START_TEXT, get_pay_keyboard())

    @staticmethod
    async def _invoice(peer: Peer, message: MessageRef, _state: None) -> MessageRef:
        parts = (message.content.message or "").split()
        if len(parts) < 2:
            return await send_bot_message(peer, f"Usage: /invoice <amount>\nAllowed: {', '.join(map(str, INVOICE_AMOUNTS))}")

        try:
            amount = int(parts[1])
        except ValueError:
            return await send_bot_message(peer, "Invalid amount. Use: /invoice 10")

        if amount not in INVOICE_AMOUNTS:
            return await send_bot_message(
                peer, f"Amount not allowed. Choose from: {', '.join(map(str, INVOICE_AMOUNTS))}",
            )

        invoice_message = await send_stars_invoice(peer, amount)
        await upd.send_message(None, {peer: invoice_message}, False)
        return await send_bot_message(peer, f"Invoice for {amount} stars sent!")