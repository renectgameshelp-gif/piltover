from piltover.app.bot_handlers.adminbot.text_handler import AdminBotTextHandler
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.adminbot.utils import home_keyboard, send_bot_message
from piltover.db.enums import AdminBotState
from piltover.db.models import AdminBotUserState, MessageRef, Peer

_START_TEXT = (
    "🛡 Admin Panel\n\n"
    "Server administration. Choose a category below."
)

_FALLBACK_TEXT = (
    "Use the buttons below or send /start to open the admin panel."
)


class AdminBotInteractionHandler(BotInteractionHandler[AdminBotState, AdminBotUserState]):
    def __init__(self) -> None:
        super().__init__(AdminBotUserState)
        self.include(AdminBotTextHandler())
        self.command("start").set_send_message_func(send_bot_message).do(self._start).register()
        self.text().set_send_message_func(send_bot_message).otherwise(self._fallback).register()

    @staticmethod
    async def _start(peer: Peer, message: MessageRef, _state: AdminBotUserState | None) -> MessageRef:
        from piltover.app.bot_handlers.adminbot import pages_extended
        text = message.content.message or ""
        args = text.split(maxsplit=1)
        if len(args) > 1 and args[1].startswith("report_"):
            try:
                report_id = int(args[1][len("report_"):])
            except ValueError:
                return await send_bot_message(peer, "Invalid report link.", home_keyboard())
            return await pages_extended.page_report(
                peer, report_id, message, list_key="r0", overlay=True,
            )

        return await send_bot_message(peer, _START_TEXT, home_keyboard())

    @staticmethod
    async def _fallback(peer: Peer, _message: MessageRef, _state: AdminBotUserState | None) -> MessageRef:
        return await send_bot_message(peer, _FALLBACK_TEXT, home_keyboard())