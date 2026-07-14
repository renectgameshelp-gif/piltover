from piltover.db.models import Peer, User
from piltover.tl import Updates


async def stars_pay_payment_success(
        payer: User, payer_peer: Peer, stars: int, title: str,
) -> Updates:
    from piltover.app.handlers.messages.sending import send_message_internal
    text = (
        f"✅ Payment successful!\n\n"
        f"You paid {stars} ⭐ for «{title}».\n"
        f"Thank you for your purchase!"
    )
    return await send_message_internal(
        payer, payer_peer, None, None, False,
        author=payer_peer.user_id, opposite=False, text=text,
    )