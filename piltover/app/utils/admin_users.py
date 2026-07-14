from __future__ import annotations

import piltover.app.utils.updates_manager as upd
from piltover.db.models import User


class LastAdminError(ValueError):
    pass


async def set_user_admin(user: User, admin: bool) -> bool:
    if user.admin == admin:
        return False

    if not admin and user.admin:
        admin_count = await User.filter(admin=True, bot=False, deleted=False).count()
        if admin_count <= 1:
            raise LastAdminError("Cannot remove the last admin")

    user.admin = admin
    await user.save(update_fields=["admin"])
    await user.inc_version()
    await upd.update_user(user)
    return True