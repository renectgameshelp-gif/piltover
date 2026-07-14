from __future__ import annotations

from typing import TYPE_CHECKING

import piltover.app.utils.updates_manager as upd

if TYPE_CHECKING:
    from piltover.db.models import User, Chat, Channel


async def set_user_verified(user: User, verified: bool) -> bool:
    if user.verified == verified:
        return False

    from piltover.db.models import State

    user.verified = verified
    await user.save(update_fields=["verified"])
    await user.inc_version()
    await State.get_or_create(user=user, defaults={"pts": 0})
    await upd.update_user(user)
    return True


async def set_chat_verified(chat: Chat, verified: bool) -> bool:
    if chat.verified == verified:
        return False

    chat.verified = verified
    chat.version += 1
    await chat.save(update_fields=["verified", "version"])
    await upd.update_chat(chat)
    return True


async def set_channel_verified(channel: Channel, verified: bool) -> bool:
    if channel.verified == verified:
        return False

    channel.verified = verified
    channel.version += 1
    await channel.save(update_fields=["verified", "version"])
    await upd.update_channel(channel)
    return True