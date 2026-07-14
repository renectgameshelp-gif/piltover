from __future__ import annotations

from piltover.db.models import User
from piltover.exceptions import ErrorRpc

ADMIN_ONLY_BOT_USERNAMES = frozenset({"admin"})


async def is_builtin_admin_bot(bot_user: User) -> bool:
    username = await bot_user.get_raw_username()
    return username in ADMIN_ONLY_BOT_USERNAMES


async def is_admin(user_id: int) -> bool:
    return await User.filter(id=user_id, admin=True, deleted=False).exists()


async def ensure_admin_bot_access(user_id: int, bot_username: str | None) -> None:
    if bot_username not in ADMIN_ONLY_BOT_USERNAMES:
        return
    if not await is_admin(user_id):
        raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")