import pytest
from pyrogram.errors import UserPrivacyRestricted
from pyrogram.raw.types import UpdateNewMessage

from piltover.app.bot_handlers.adminbot.callback_handler import adminbot_callback_query_handler
from piltover.app.bot_handlers.adminbot.utils import send_bot_message
from piltover.app.utils.admin_access import ensure_admin_bot_access, is_admin
from piltover.app.utils.admin_users import LastAdminError, set_user_admin
from piltover.db.models import Peer, User
from piltover.exceptions import ErrorRpc
from tests.client import TestClient


@pytest.mark.asyncio
async def test_ensure_admin_bot_access_blocks_non_admin() -> None:
    user = await User.create(phone_number="900000001", first_name="Regular", admin=False)
    with pytest.raises(ErrorRpc) as exc:
        await ensure_admin_bot_access(user.id, "admin")
    assert exc.value.error_message == "USER_PRIVACY_RESTRICTED"


@pytest.mark.asyncio
async def test_ensure_admin_bot_access_allows_admin() -> None:
    user = await User.create(phone_number="900000002", first_name="Admin", admin=True)
    await ensure_admin_bot_access(user.id, "admin")
    assert await is_admin(user.id)


@pytest.mark.asyncio
async def test_cannot_remove_last_admin() -> None:
    user = await User.create(phone_number="900000003", first_name="Solo", admin=True)
    with pytest.raises(LastAdminError):
        await set_user_admin(user, False)


@pytest.mark.asyncio
async def test_adminbot_start_for_admin() -> None:
    async with TestClient(phone_number="123456789") as client:
        user = await User.get(phone_number=client.phone_number)
        user.admin = True
        await user.save(update_fields=["admin"])

        bot = await client.get_users("admin")
        await client.send_message(bot.id, "/start")

        user_message = await client.expect_update(UpdateNewMessage)
        bot_message = await client.expect_update(UpdateNewMessage)

        if user_message.message.from_id.user_id != client.me.id:
            user_message, bot_message = bot_message, user_message

        assert "Admin Panel" in bot_message.message.message


@pytest.mark.asyncio
async def test_adminbot_blocks_non_admin_message() -> None:
    async with TestClient(phone_number="123456789") as client:
        admin_user = await User.get(phone_number=client.phone_number)
        admin_user.admin = True
        await admin_user.save(update_fields=["admin"])

    async with TestClient(phone_number="444555666") as client:
        user = await User.get(phone_number=client.phone_number)
        assert user.admin is False

        bot = await client.get_users("admin")
        with pytest.raises(UserPrivacyRestricted):
            await client.send_message(bot.id, "/start")


@pytest.mark.asyncio
async def test_adminbot_grant_admin_callback() -> None:
    target = await User.create(phone_number="900000004", first_name="Target", admin=False)

    async with TestClient(phone_number="123456789") as client:
        admin_user = await User.get(phone_number=client.phone_number)
        admin_user.admin = True
        await admin_user.save(update_fields=["admin"])

        bot = await client.get_users("admin")
        peer = await Peer.get(owner_id=admin_user.id, user_id=bot.id)
        menu = await send_bot_message(peer, "menu", None)

        answer = await adminbot_callback_query_handler(
            peer, menu, f"adm:act:admin:{target.id}".encode(),
        )
        assert answer is not None
        assert "granted" in (answer.message or "").lower()

        await target.refresh_from_db()
        assert target.admin is True