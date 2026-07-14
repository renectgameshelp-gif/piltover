from types import NoneType

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.verifybot.utils import main_menu_keyboard, send_bot_message
from piltover.db.models import MessageRef, Peer

_START_TEXT = (
    "✅ Verification Bot\n\n"
    "Grant or remove the verified checkmark for your account, bots, "
    "and groups or channels you created."
)


class VerifyBotInteractionHandler(BotInteractionHandler[NoneType, NoneType]):
    def __init__(self) -> None:
        super().__init__(None)
        self.command("start").set_send_message_func(send_bot_message).do(self._start).register()

    @staticmethod
    async def _start(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        return await send_bot_message(peer, _START_TEXT, main_menu_keyboard())