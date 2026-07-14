from __future__ import annotations

from piltover.db.models import Bot, User


async def resolve_bot_token(token: str) -> tuple[Bot, User] | None:
    token_parts = token.split(":", 1)
    if len(token_parts) != 2:
        return None
    bot_id, token_nonce = token_parts
    if not bot_id.isdigit():
        return None

    bot = await Bot.get_or_none(bot_id=int(bot_id), token_nonce=token_nonce).select_related("bot")
    if bot is None:
        return None
    return bot, bot.bot