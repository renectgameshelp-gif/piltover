from __future__ import annotations

from time import time
from uuid import uuid4

from tortoise.transactions import in_transaction

from piltover.context import request_ctx
from piltover.db.enums import StarsPaymentPurpose, StarsTransactionPeerType, MediaType, MessageType
from piltover.db.models import (
    UserStarsBalance, StarsTransaction, StarsPaymentForm, User, Peer, MessageRef,
    BotPrecheckoutQuery, Username,
)
from piltover.db.enums import PeerType
from piltover.db.models.stars_transaction import StarsTransactionRenderContext
from piltover.exceptions import ErrorRpc
from piltover.tl import (
    StarsAmount, InputInvoiceStars, InputStorePaymentStarsTopup, InputStorePaymentStarsGift,
    InputInvoiceMessage, Invoice, LabeledPrice, MessageMediaInvoice, PaymentCharge,
    MessageActionPaymentSentMe, MessageActionPaymentSent,
)
from piltover.tl.types.payments import PaymentForm, PaymentFormStars, StarsStatus
from piltover.utils.users_chats_channels import UsersChatsChannels

SYSTEM_STARS_BOT_ID = 777000
STARS_CURRENCY = "XTR"
STARS_PAYMENT_URL = "https://example.org"
PRECHECKOUT_TIMEOUT_SECONDS = 10

_stars_bot_user_id: int | None = None


async def get_stars_bot_user_id() -> int:
    global _stars_bot_user_id
    if _stars_bot_user_id is None:
        username = await Username.get_or_none(username="stars")
        user_id = username.user_id if username is not None else None
        if user_id is None:
            raise RuntimeError("Stars bot is not configured")
        _stars_bot_user_id = user_id
    return _stars_bot_user_id

async def ensure_wallet_user_id(user_id: int, peer: object) -> int:
    peer_type, peer_owner_id = Peer.type_and_id_from_input_raise(user_id, peer)
    if peer_type is not PeerType.SELF:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    return peer_owner_id


async def build_stars_status(
        wallet_user_id: int,
        *,
        history: list[StarsTransaction] | None = None,
        next_offset: str | None = None,
        subscriptions: list | None = None,
        subscriptions_next_offset: str | None = None,
) -> StarsStatus:
    balance = await UserStarsBalance.get_or_create_for(wallet_user_id)
    users: list = []
    chats: list = []

    history_tl = None
    if history is not None:
        ucc = UsersChatsChannels()
        render_ctx = StarsTransactionRenderContext(stars_bot_user_id=await get_stars_bot_user_id())
        history_tl = [tx.to_tl(ucc, render_ctx) for tx in history]
        users, chats_list, channels = await ucc.resolve()
        chats = [*chats_list, *channels]

    return StarsStatus(
        balance=balance.to_stars_amount(),
        history=history_tl,
        next_offset=next_offset,
        subscriptions=subscriptions,
        subscriptions_next_offset=subscriptions_next_offset,
        chats=chats,
        users=users,
    )


async def fetch_transactions(
        wallet_user_id: int,
        *,
        inbound: bool,
        outbound: bool,
        ascending: bool,
        offset: str,
        limit: int,
        subscription_id: str | None = None,
) -> tuple[list[StarsTransaction], str | None]:
    if subscription_id is not None:
        return [], None

    limit = min(max(limit, 1), 50)
    query = StarsTransaction.filter(user_id=wallet_user_id)
    if inbound and not outbound:
        query = query.filter(inbound=True)
    elif outbound and not inbound:
        query = query.filter(inbound=False)

    if offset:
        offset_tx = await StarsTransaction.get_or_none(transaction_id=offset, user_id=wallet_user_id)
        if offset_tx is not None:
            if ascending:
                query = query.filter(date__gt=offset_tx.date)
            else:
                query = query.filter(date__lt=offset_tx.date)

    order = "date" if ascending else "-date"
    rows = await query.order_by(order).limit(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_offset = rows[-1].transaction_id if has_more and rows else None
    return rows, next_offset


async def fetch_transactions_by_id(wallet_user_id: int, transaction_ids: list[str]) -> list[StarsTransaction]:
    if not transaction_ids:
        return []
    rows = await StarsTransaction.filter(
        user_id=wallet_user_id,
        transaction_id__in=transaction_ids,
    ).all()
    order = {tx_id: idx for idx, tx_id in enumerate(transaction_ids)}
    rows.sort(key=lambda row: order.get(row.transaction_id, len(transaction_ids)))
    return rows


def _invoice_for_stars(stars: int) -> Invoice:
    return Invoice(
        currency=STARS_CURRENCY,
        prices=[LabeledPrice(label="Stars", amount=stars)],
    )


async def _parse_stars_invoice(
        user_id: int, invoice: object,
) -> tuple[StarsPaymentPurpose, int, str, int, int | None]:
    if not isinstance(invoice, InputInvoiceStars):
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")

    purpose = invoice.purpose
    if isinstance(purpose, InputStorePaymentStarsTopup):
        if purpose.stars <= 0:
            raise ErrorRpc(error_code=400, error_message="STARS_AMOUNT_INVALID")
        return StarsPaymentPurpose.TOPUP, purpose.stars, purpose.currency, purpose.amount, None

    if isinstance(purpose, InputStorePaymentStarsGift):
        if purpose.stars <= 0:
            raise ErrorRpc(error_code=400, error_message="STARS_AMOUNT_INVALID")
        gift_peer = await Peer.query_from_input_user_or_raise(user_id, purpose.user_id).only("user_id")
        return StarsPaymentPurpose.GIFT, purpose.stars, purpose.currency, purpose.amount, gift_peer.user_id

    raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")


def _invoice_for_fiat(currency: str, amount: int) -> Invoice:
    return Invoice(
        currency=currency,
        prices=[LabeledPrice(label="Stars", amount=amount)],
    )


async def create_payment_form(user_id: int, invoice: object) -> PaymentForm | PaymentFormStars:
    if isinstance(invoice, InputInvoiceMessage):
        return await _create_bot_payment_form(user_id, invoice)
    purpose, stars, currency, amount, gift_user_id = await _parse_stars_invoice(user_id, invoice)

    if purpose is StarsPaymentPurpose.GIFT:
        if gift_user_id is None or not await User.filter(id=gift_user_id).exists():
            raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
        title = "Gift Telegram Stars"
        description = f"Gift {stars} Telegram Stars"
    else:
        title = "Top Up Telegram Stars"
        description = f"Buy {stars} Telegram Stars"

    form = await StarsPaymentForm.create_form(
        user_id=user_id,
        purpose=purpose,
        stars=stars,
        currency=currency,
        amount=amount,
        gift_user_id=gift_user_id,
    )

    if currency == STARS_CURRENCY:
        return PaymentFormStars(
            form_id=form.id,
            bot_id=SYSTEM_STARS_BOT_ID,
            title=title,
            description=description,
            invoice=_invoice_for_stars(stars),
            users=[],
        )

    return PaymentForm(
        form_id=form.id,
        bot_id=SYSTEM_STARS_BOT_ID,
        title=title,
        description=description,
        invoice=_invoice_for_fiat(currency, amount),
        provider_id=SYSTEM_STARS_BOT_ID,
        url=STARS_PAYMENT_URL,
        users=[],
    )


async def grant_stars(
        user_id: int,
        stars: int,
        *,
        title: str = "Stars Bonus",
        description: str | None = None,
) -> UserStarsBalance:
    stars_bot_id = await get_stars_bot_user_id()
    balance, _ = await _credit_stars(
        user_id,
        stars,
        inbound=True,
        peer_type=StarsTransactionPeerType.PEER,
        title=title,
        description=description or f"Received {stars} Telegram Stars",
        peer_user_id=stars_bot_id,
    )
    return balance


async def spend_stars(
        user_id: int,
        stars: int,
        *,
        peer_type: StarsTransactionPeerType,
        title: str,
        description: str | None = None,
        gift: bool = False,
        peer_user_id: int | None = None,
) -> UserStarsBalance:
    balance, _ = await _debit_stars(
        user_id,
        stars,
        peer_type=peer_type,
        title=title,
        description=description,
        gift=gift,
        peer_user_id=peer_user_id,
    )
    return balance


def _invoice_total_amount(invoice: Invoice) -> int:
    return sum(price.amount for price in invoice.prices)


def _pack_invoice_static(invoice_tl: MessageMediaInvoice, payload: bytes) -> bytes:
    return invoice_tl.write() + b"\0" + payload


def _unpack_invoice_static(data: bytes) -> tuple[MessageMediaInvoice, bytes]:
    from io import BytesIO
    invoice_bytes, payload = data.split(b"\0", 1)
    return MessageMediaInvoice.read(BytesIO(invoice_bytes)), payload


async def _load_bot_invoice_message(user_id: int, invoice: InputInvoiceMessage) -> tuple[MessageRef, MessageMediaInvoice, bytes, int]:
    peer = await Peer.from_input_peer_raise(user_id, invoice.peer)
    message = await MessageRef.get_(
        invoice.msg_id, peer, prefetch=("content__media", "content__author"),
    )
    if message is None or not message.content.author.bot:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    media = message.content.media
    if media is None or media.type is not MediaType.INVOICE or media.static_data is None:
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")

    invoice_media, payload = _unpack_invoice_static(media.static_data)
    if invoice_media.currency != STARS_CURRENCY:
        raise ErrorRpc(error_code=400, error_message="CURRENCY_TOTAL_AMOUNT_INVALID")

    return message, invoice_media, payload, message.content.author_id


async def _create_bot_payment_form(user_id: int, invoice: InputInvoiceMessage) -> PaymentFormStars:
    message, invoice_media, payload, bot_user_id = await _load_bot_invoice_message(user_id, invoice)
    stars = invoice_media.total_amount

    form = await StarsPaymentForm.create_form(
        user_id=user_id,
        purpose=StarsPaymentPurpose.BOT_INVOICE,
        stars=stars,
        currency=invoice_media.currency,
        amount=stars,
        bot_user_id=bot_user_id,
        message_id=message.id,
        payload=payload,
    )

    ucc = UsersChatsChannels()
    ucc.add_user(bot_user_id)
    users, _, _ = await ucc.resolve()

    return PaymentFormStars(
        form_id=form.id,
        bot_id=bot_user_id,
        title=invoice_media.title,
        description=invoice_media.description,
        invoice=Invoice(
            currency=invoice_media.currency,
            prices=[LabeledPrice(label=invoice_media.title, amount=stars)],
        ),
        users=users,
    )


async def _await_bot_precheckout(
        bot_user_id: int, payer_user_id: int, payload: bytes, currency: str, total_amount: int,
) -> None:
    bot = await User.get(id=bot_user_id).only("id", "system")
    if bot.system:
        return

    import piltover.app.utils.updates_manager as upd
    from piltover.utils.snowflake import Snowflake

    ctx = request_ctx.get()
    pubsub = ctx.worker.pubsub
    query = await BotPrecheckoutQuery.create(
        id=Snowflake.make_id(),
        user_id=payer_user_id,
        bot_id=bot_user_id,
        payload=payload,
        currency=currency,
        total_amount=total_amount,
    )

    topic = f"bot-precheckout-query/{query.id}"
    await pubsub.listen(topic, None)
    await upd.bot_precheckout_query(bot_user_id, query)

    result = await pubsub.listen(topic, PRECHECKOUT_TIMEOUT_SECONDS)
    await query.delete()
    if result is None:
        raise ErrorRpc(error_code=400, error_message="BOT_PRECHECKOUT_TIMEOUT")
    if result != b"1":
        raise ErrorRpc(error_code=400, error_message=result.decode("utf-8", errors="replace") or "PAYMENT_FAILED")


async def _send_bot_payment_messages(
        payer: User, bot_user_id: int, peer: Peer, invoice_message_id: int,
        stars: int, payload: bytes, charge_id: str,
) -> None:
    from piltover.app.handlers.messages.sending import send_message_internal

    charge = PaymentCharge(id=charge_id, provider_charge_id=charge_id)
    payer_peer, _ = await Peer.get_or_create(owner=payer, user_id=bot_user_id, type=PeerType.USER)
    bot = await User.get(id=bot_user_id).only("id", "bot")

    await send_message_internal(
        payer, payer_peer, None, invoice_message_id, False, author=bot_user_id,
        type=MessageType.SERVICE_PAYMENT,
        extra_info=MessageActionPaymentSentMe(
            currency=STARS_CURRENCY,
            total_amount=stars,
            payload=payload,
            charge=charge,
        ).write(),
    )

    bot_peer, _ = await Peer.get_or_create(owner=bot, user_id=payer.id, type=PeerType.USER)
    await send_message_internal(
        bot, bot_peer, None, None, False, author=payer.id,
        type=MessageType.SERVICE_PAYMENT,
        extra_info=MessageActionPaymentSent(
            currency=STARS_CURRENCY,
            total_amount=stars,
            invoice_slug=None,
        ).write(),
    )


async def _credit_stars(
        wallet_user_id: int,
        stars: int,
        *,
        inbound: bool,
        peer_type: StarsTransactionPeerType,
        title: str,
        description: str | None = None,
        gift: bool = False,
        peer_user_id: int | None = None,
        msg_id: int | None = None,
        bot_payload: bytes | None = None,
) -> tuple[UserStarsBalance, StarsTransaction]:
    async with in_transaction():
        balance = await UserStarsBalance.filter(user_id=wallet_user_id).select_for_update().first()
        if balance is None:
            balance = await UserStarsBalance.create(user_id=wallet_user_id, amount=0, nanos=0)

        balance.amount += stars
        await balance.save(update_fields=["amount"])

        tx = await StarsTransaction.create(
            transaction_id=StarsTransaction.gen_id(),
            user_id=wallet_user_id,
            stars_amount=stars,
            inbound=inbound,
            date=int(time()),
            peer_type=peer_type,
            peer_user_id=peer_user_id,
            title=title,
            description=description,
            gift=gift,
            msg_id=msg_id,
            bot_payload=bot_payload,
        )

    return balance, tx


async def _debit_stars(
        wallet_user_id: int,
        stars: int,
        *,
        peer_type: StarsTransactionPeerType,
        title: str,
        description: str | None = None,
        gift: bool = False,
        peer_user_id: int | None = None,
        msg_id: int | None = None,
        bot_payload: bytes | None = None,
) -> tuple[UserStarsBalance, StarsTransaction]:
    if stars <= 0:
        raise ErrorRpc(error_code=400, error_message="STARS_AMOUNT_INVALID")

    async with in_transaction():
        balance = await UserStarsBalance.filter(user_id=wallet_user_id).select_for_update().first()
        if balance is None or balance.amount < stars:
            raise ErrorRpc(error_code=400, error_message="BALANCE_TOO_LOW")

        balance.amount -= stars
        await balance.save(update_fields=["amount"])

        tx = await StarsTransaction.create(
            transaction_id=StarsTransaction.gen_id(),
            user_id=wallet_user_id,
            stars_amount=stars,
            inbound=False,
            date=int(time()),
            peer_type=peer_type,
            peer_user_id=peer_user_id,
            title=title,
            description=description,
            gift=gift,
            msg_id=msg_id,
            bot_payload=bot_payload,
        )

    return balance, tx


async def complete_payment_form(user_id: int, form_id: int, invoice: object) -> tuple[UserStarsBalance, list[int]]:
    if isinstance(invoice, InputInvoiceMessage):
        return await _complete_bot_payment_form(user_id, form_id, invoice)

    purpose, stars, _currency, _amount, gift_user_id = await _parse_stars_invoice(user_id, invoice)

    form = await StarsPaymentForm.get_or_none(id=form_id, user_id=user_id)
    if form is None:
        raise ErrorRpc(error_code=400, error_message="FORM_EXPIRED")
    if form.is_expired():
        await form.delete()
        raise ErrorRpc(error_code=400, error_message="FORM_EXPIRED")
    if form.purpose != purpose or form.stars != stars:
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")
    if purpose is StarsPaymentPurpose.GIFT and form.gift_user_id != gift_user_id:
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")

    await form.delete()

    updated_user_ids: list[int] = []
    paid_with_stars = form.currency == STARS_CURRENCY

    if purpose is StarsPaymentPurpose.TOPUP:
        if paid_with_stars:
            raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")
        balance, _ = await _credit_stars(
            user_id,
            stars,
            inbound=True,
            peer_type=StarsTransactionPeerType.FRAGMENT,
            title="Stars Top-Up",
            description=f"Purchased {stars} Telegram Stars",
        )
        updated_user_ids.append(user_id)
        return balance, updated_user_ids

    assert gift_user_id is not None
    if paid_with_stars:
        payer_balance, _ = await _debit_stars(
            user_id,
            stars,
            peer_type=StarsTransactionPeerType.PEER,
            title="Stars Gift",
            description=f"Gifted {stars} Telegram Stars",
            gift=True,
            peer_user_id=gift_user_id,
        )
        updated_user_ids.append(user_id)
    else:
        payer_balance = await UserStarsBalance.get_or_create_for(user_id)

    recipient_balance, _ = await _credit_stars(
        gift_user_id,
        stars,
        inbound=True,
        peer_type=StarsTransactionPeerType.PEER,
        title="Stars Gift",
        description=f"Received {stars} Telegram Stars",
        gift=True,
        peer_user_id=user_id,
    )
    updated_user_ids.append(gift_user_id)
    return payer_balance if paid_with_stars else recipient_balance, updated_user_ids


async def _complete_bot_payment_form(
        user_id: int, form_id: int, invoice: InputInvoiceMessage,
) -> tuple[UserStarsBalance, list[int]]:
    message, invoice_media, payload, bot_user_id = await _load_bot_invoice_message(user_id, invoice)
    stars = invoice_media.total_amount

    form = await StarsPaymentForm.get_or_none(id=form_id, user_id=user_id)
    if form is None:
        raise ErrorRpc(error_code=400, error_message="FORM_EXPIRED")
    if form.is_expired():
        await form.delete()
        raise ErrorRpc(error_code=400, error_message="FORM_EXPIRED")
    if form.purpose is not StarsPaymentPurpose.BOT_INVOICE:
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")
    if form.stars != stars or form.bot_user_id != bot_user_id or form.message_id != message.id:
        raise ErrorRpc(error_code=400, error_message="INVOICE_INVALID")

    await _await_bot_precheckout(bot_user_id, user_id, payload, invoice_media.currency, stars)
    await form.delete()

    payer = await User.get(id=user_id).only("id", "bot", "first_name")
    peer = await Peer.from_input_peer_raise(user_id, invoice.peer)
    charge_id = uuid4().hex

    payer_balance, _ = await _debit_stars(
        user_id,
        stars,
        peer_type=StarsTransactionPeerType.PREMIUM_BOT,
        title=invoice_media.title,
        description=invoice_media.description,
        peer_user_id=bot_user_id,
        msg_id=message.id,
        bot_payload=payload or None,
    )
    await _credit_stars(
        bot_user_id,
        stars,
        inbound=True,
        peer_type=StarsTransactionPeerType.PEER,
        title=invoice_media.title,
        description=f"Payment from user {user_id}",
        peer_user_id=user_id,
        msg_id=message.id,
        bot_payload=payload or None,
    )

    await _send_bot_payment_messages(payer, bot_user_id, peer, message.id, stars, payload, charge_id)

    return payer_balance, [user_id, bot_user_id]