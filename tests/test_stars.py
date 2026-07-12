import pytest

from piltover.app.utils import stars_manager as stars
from piltover.db.enums import StarsTransactionPeerType
from piltover.db.models import StarsTransaction, User
from piltover.utils.users_chats_channels import UsersChatsChannels


@pytest.mark.asyncio
async def test_grant_stars_records_inbound_transaction(client_with_auth) -> None:
    client = await client_with_auth()
    user = await User.get(phone_number=client.phone_number)

    await stars.grant_stars(user.id, 50, title="Test Bonus")

    tx = await StarsTransaction.filter(user_id=user.id).first()
    assert tx is not None
    assert tx.inbound is True
    assert tx.stars_amount == 50
    assert tx.peer_type is StarsTransactionPeerType.PEER
    assert tx.peer_user_id is not None

    ucc = UsersChatsChannels()
    from piltover.app.utils.stars_manager import get_stars_bot_user_id
    from piltover.db.models.stars_transaction import StarsTransactionRenderContext

    render_ctx = StarsTransactionRenderContext(stars_bot_user_id=await get_stars_bot_user_id())
    tl_tx = tx.to_tl(ucc, render_ctx)
    assert tl_tx.stars.amount == 50
    users, _, _ = await ucc.resolve()
    assert users


@pytest.mark.asyncio
async def test_spend_stars_records_outbound_transaction(client_with_auth) -> None:
    client = await client_with_auth()
    user = await User.get(phone_number=client.phone_number)

    await stars.grant_stars(user.id, 100)
    await stars.spend_stars(
        user.id,
        25,
        peer_type=StarsTransactionPeerType.PEER,
        title="Test Spend",
        peer_user_id=user.id,
    )

    outbound = await StarsTransaction.filter(user_id=user.id, inbound=False).first()
    assert outbound is not None
    assert outbound.stars_amount == 25

    ucc = UsersChatsChannels()
    tl_tx = outbound.to_tl(ucc)
    assert tl_tx.stars.amount == -25


@pytest.mark.asyncio
async def test_fetch_transactions_filters_direction(client_with_auth) -> None:
    client = await client_with_auth()
    user = await User.get(phone_number=client.phone_number)

    await stars.grant_stars(user.id, 10)
    await stars.spend_stars(
        user.id,
        3,
        peer_type=StarsTransactionPeerType.API,
        title="Spend",
    )

    inbound_rows, _ = await stars.fetch_transactions(
        user.id, inbound=True, outbound=False, ascending=False, offset="", limit=50,
    )
    outbound_rows, _ = await stars.fetch_transactions(
        user.id, inbound=False, outbound=True, ascending=False, offset="", limit=50,
    )

    assert len(inbound_rows) == 1
    assert inbound_rows[0].inbound is True
    assert len(outbound_rows) == 1
    assert outbound_rows[0].inbound is False


@pytest.mark.asyncio
async def test_fetch_transactions_by_id_preserves_order(client_with_auth) -> None:
    client = await client_with_auth()
    user = await User.get(phone_number=client.phone_number)

    await stars.grant_stars(user.id, 5)
    await stars.grant_stars(user.id, 15)

    all_rows = await StarsTransaction.filter(user_id=user.id).order_by("-date")
    assert len(all_rows) == 2

    rows = await stars.fetch_transactions_by_id(
        user.id,
        [all_rows[1].transaction_id, all_rows[0].transaction_id],
    )
    assert [row.transaction_id for row in rows] == [
        all_rows[1].transaction_id,
        all_rows[0].transaction_id,
    ]