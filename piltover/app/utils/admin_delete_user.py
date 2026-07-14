from __future__ import annotations

from tortoise.expressions import F

from piltover.app.utils.admin_sessions import kick_all_user_sessions
from piltover.db.models import BlockedPhone, Bot, DeletedAccountSnapshot, User, Username
from piltover.db.models.bot import bot_gen_token


class RestoreAccountError(Exception):
    pass


async def save_deleted_account_snapshot(user: User) -> None:
    username = await user.get_raw_username()
    bot_owner_id = None
    bot_token_nonce = None
    if user.bot:
        bot_row = await Bot.get_or_none(bot_id=user.id)
        if bot_row is not None:
            bot_owner_id = bot_row.owner_id
            bot_token_nonce = bot_row.token_nonce

    await DeletedAccountSnapshot.update_or_create(
        user_id=user.id,
        defaults={
            "phone_number": user.phone_number,
            "first_name": user.first_name or ("Deleted Bot" if user.bot else "Deleted Account"),
            "last_name": user.last_name,
            "about": user.about,
            "bot": user.bot,
            "username": username,
            "bot_owner_id": bot_owner_id,
            "bot_token_nonce": bot_token_nonce,
            "verified": user.verified,
            "admin": user.admin,
            "spam_blocked": user.spam_blocked,
        },
    )


async def admin_delete_user(user: User) -> int:
    await save_deleted_account_snapshot(user)

    phone = user.phone_number
    sessions_kicked = await kick_all_user_sessions(user.id)

    await User.filter(id=user.id).update(
        deleted=True,
        phone_number=None,
        first_name="Deleted Account",
        last_name=None,
        about=None,
        birthday=None,
        admin=False,
        verified=False,
        spam_blocked=False,
        version=F("version") + 1,
    )

    if phone:
        await BlockedPhone.update_or_create(
            phone_number=phone,
            defaults={"user_id": user.id},
        )

    return sessions_kicked


async def admin_restore_user(user: User) -> None:
    if not user.deleted or user.bot or user.system:
        raise RestoreAccountError("User not found or not restorable.")

    snapshot = await DeletedAccountSnapshot.get_or_none(user_id=user.id)
    phone = snapshot.phone_number if snapshot else None

    if phone and await User.filter(phone_number=phone, deleted=False).exclude(id=user.id).exists():
        raise RestoreAccountError("Phone number is already in use.")

    first_name = snapshot.first_name if snapshot else "Restored User"
    if first_name in ("", "Deleted Account"):
        first_name = "Restored User"

    await User.filter(id=user.id).update(
        deleted=False,
        phone_number=phone,
        first_name=first_name,
        last_name=snapshot.last_name if snapshot else None,
        about=snapshot.about if snapshot else None,
        verified=snapshot.verified if snapshot else False,
        admin=snapshot.admin if snapshot else False,
        spam_blocked=snapshot.spam_blocked if snapshot else False,
        version=F("version") + 1,
    )

    if phone:
        await BlockedPhone.filter(user_id=user.id).delete()
        await BlockedPhone.filter(phone_number=phone).delete()

    if snapshot is not None:
        await snapshot.delete()

    user = await User.get(id=user.id)
    import piltover.app.utils.updates_manager as upd
    await upd.update_user(user)


async def admin_restore_bot(bot_user: User) -> None:
    if not bot_user.deleted or not bot_user.bot or bot_user.system:
        raise RestoreAccountError("Bot not found or not restorable.")

    snapshot = await DeletedAccountSnapshot.get_or_none(user_id=bot_user.id)

    first_name = snapshot.first_name if snapshot else "Restored Bot"
    if first_name in ("", "Deleted Bot"):
        first_name = "Restored Bot"

    username = snapshot.username if snapshot else None
    if username and await Username.filter(username=username).exclude(user_id=bot_user.id).exists():
        raise RestoreAccountError(f"Username @{username} is already taken.")

    await User.filter(id=bot_user.id).update(
        deleted=False,
        first_name=first_name,
        last_name=snapshot.last_name if snapshot else None,
        about=snapshot.about if snapshot else None,
        verified=snapshot.verified if snapshot else False,
        version=F("version") + 1,
    )

    owner_id = snapshot.bot_owner_id if snapshot else None
    if owner_id is not None and not await User.filter(id=owner_id, deleted=False).exists():
        owner_id = None

    if owner_id is not None:
        token_nonce = snapshot.bot_token_nonce if snapshot else bot_gen_token()
        await Bot.update_or_create(
            bot_id=bot_user.id,
            defaults={"owner_id": owner_id, "token_nonce": token_nonce},
        )

    if username:
        await Username.update_or_create(
            user_id=bot_user.id,
            defaults={"username": username},
        )

    if snapshot is not None:
        await snapshot.delete()

    bot_user = await User.get(id=bot_user.id)
    import piltover.app.utils.updates_manager as upd
    await upd.update_user(bot_user)


async def is_phone_banned(phone_number: str) -> bool:
    return await BlockedPhone.filter(phone_number=phone_number).exists()