import pytest
from pyrogram.errors import InputUserDeactivated
from pyrogram.raw.functions.phone import RequestCall
from pyrogram.raw.types import InputUser, PhoneCallProtocol

from piltover.app.bot_handlers.adminbot.actions import restore_deleted_account_action
from piltover.app.bot_handlers.adminbot.utils import send_bot_message
from piltover.app.utils.admin_channel_ops import admin_delete_bot
from piltover.app.utils.admin_delete_user import admin_delete_user, admin_restore_bot, admin_restore_user
from piltover.db.models import BlockedPhone, Bot, DeletedAccountSnapshot, Peer, User, Username
from tests.client import TestClient


@pytest.mark.asyncio
async def test_admin_delete_and_restore_user() -> None:
    user = await User.create(phone_number="900000030", first_name="RestoreMe", bot=False)
    await admin_delete_user(user)

    await user.refresh_from_db()
    assert user.deleted
    assert await DeletedAccountSnapshot.filter(user_id=user.id).exists()
    assert await BlockedPhone.filter(user_id=user.id).exists()

    await admin_restore_user(await User.get(id=user.id))
    await user.refresh_from_db()

    assert not user.deleted
    assert user.phone_number == "900000030"
    assert user.first_name == "RestoreMe"
    assert not await BlockedPhone.filter(user_id=user.id).exists()
    assert not await DeletedAccountSnapshot.filter(user_id=user.id).exists()


@pytest.mark.asyncio
async def test_admin_delete_and_restore_bot() -> None:
    owner = await User.create(phone_number="900000031", first_name="Owner", bot=False)
    bot_user = await User.create(phone_number=None, first_name="MyBot", bot=True)
    await Username.create(user_id=bot_user.id, username="restore_test_bot")
    await Bot.create(owner_id=owner.id, bot_id=bot_user.id)

    await admin_delete_bot(bot_user)
    await bot_user.refresh_from_db()

    assert bot_user.deleted
    assert not await Bot.filter(bot_id=bot_user.id).exists()
    assert not await Username.filter(user_id=bot_user.id).exists()
    assert await DeletedAccountSnapshot.filter(user_id=bot_user.id).exists()

    await admin_restore_bot(await User.get(id=bot_user.id))
    await bot_user.refresh_from_db()

    assert not bot_user.deleted
    assert bot_user.first_name == "MyBot"
    assert await Bot.filter(bot_id=bot_user.id, owner_id=owner.id).exists()
    assert await Username.filter(user_id=bot_user.id, username="restore_test_bot").exists()


@pytest.mark.asyncio
async def test_admin_restore_action_from_deleted_list() -> None:
    user = await User.create(phone_number="900000032", first_name="PanelRestore", bot=False)
    await admin_delete_user(user)

    async with TestClient(phone_number="123456789") as client:
        admin_user = await User.get(phone_number=client.phone_number)
        admin_user.admin = True
        await admin_user.save(update_fields=["admin"])

        bot = await client.get_users("admin")
        peer = await Peer.get(owner_id=admin_user.id, user_id=bot.id)
        menu = await send_bot_message(peer, "menu", None)

        answer = await restore_deleted_account_action(peer, menu, user.id, list_key="d0")
        assert answer is not None
        assert "restored" in (answer.message or "").lower()

        await user.refresh_from_db()
        assert not user.deleted


@pytest.mark.asyncio
async def test_cannot_call_deleted_user() -> None:
    from piltover.db.models import UserAuthorization

    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        caller = await User.get(phone_number=client1.phone_number)
        target = await User.get(phone_number=client2.phone_number)
        auth = await UserAuthorization.filter(user_id=caller.id).first()
        assert auth is not None
        access_hash = User.make_access_hash(caller.id, auth.id, target.id)
        await Peer.create(owner_id=caller.id, user_id=target.id, type=1)
        await admin_delete_user(target)

        with pytest.raises(InputUserDeactivated):
            await client1.invoke(RequestCall(
                user_id=InputUser(user_id=target.id, access_hash=access_hash),
                random_id=12345,
                g_a_hash=b"\x00" * 32,
                protocol=PhoneCallProtocol(
                    udp_p2p=True, udp_reflector=True, min_layer=92, max_layer=92, library_versions=["2.7.7"],
                ),
            ))