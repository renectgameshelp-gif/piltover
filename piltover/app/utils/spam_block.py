from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.expressions import Q

from piltover.db.enums import PeerType
from piltover.db.models import MessageRef, PhoneCall, User
from piltover.exceptions import ErrorRpc

if TYPE_CHECKING:
    from piltover.db.models import Peer


async def user_spam_blocked(user: User) -> bool:
    if hasattr(user, "spam_blocked"):
        return user.spam_blocked
    values = await User.filter(id=user.id).limit(1).values_list("spam_blocked", flat=True)
    return bool(values[0] if values else False)


async def set_user_spam_blocked(user: User, blocked: bool) -> bool:
    if await user_spam_blocked(user) == blocked:
        return False

    user.spam_blocked = blocked
    await user.save(update_fields=["spam_blocked"])
    await user.inc_version()
    import piltover.app.utils.updates_manager as upd
    await upd.update_user(user)
    return True


async def _peer_allows_spam_blocked_send(peer: Peer, user_id: int) -> bool:
    if peer.type is PeerType.CHAT:
        await peer.fetch_related("chat")
        participant = await peer.chat.get_participant(user_id)
        if participant is None:
            return False
        return peer.chat.creator_id == user_id or participant.is_admin

    if peer.type is PeerType.CHANNEL:
        await peer.fetch_related("channel")
        participant = await peer.channel.get_participant(user_id)
        if participant is None:
            return False
        return peer.channel.creator_id == user_id or participant.is_admin

    return False


async def peer_has_incoming_contact(peer: Peer, user_id: int) -> bool:
    """True when the other party messaged or called this user first in the dialog."""
    if peer.type is not PeerType.USER:
        return False

    other_id = peer.user_id
    dialog_peers = Q(peer__owner_id=user_id, peer__user_id=other_id) | Q(
        peer__owner_id=other_id, peer__user_id=user_id,
    )
    if await MessageRef.filter(
            dialog_peers, peer__type=PeerType.USER, content__author_id=other_id,
    ).exists():
        return True

    return await PhoneCall.filter(from_user_id=other_id, to_user_id=user_id).exists()


async def _reply_to_incoming_message(
        peer: Peer, user_id: int, reply_to_message_id: int,
) -> bool:
    reply_to = await MessageRef.get_or_none(
        peer_id=peer.id, id=reply_to_message_id,
    ).select_related("content")
    if reply_to is None:
        return False
    return reply_to.content.author_id != user_id


async def check_spam_blocked_creation(user: User) -> None:
    if user.bot or not await user_spam_blocked(user):
        return
    raise ErrorRpc(error_code=403, error_message="USER_RESTRICTED")


def raise_spam_blocked_send_error() -> None:
    raise ErrorRpc(error_code=400, error_message="PEER_FLOOD")


async def check_user_spam_blocked(
        user: User, peer: Peer | None = None, *, reply_to_message_id: int | None = None,
) -> None:
    if user.bot or not await user_spam_blocked(user):
        return

    if peer is not None:
        if peer.type is PeerType.USER:
            await peer.fetch_related("user")
            if peer.user.bot:
                return

            if await peer_has_incoming_contact(peer, user.id):
                return

        if peer.type in (PeerType.CHAT, PeerType.CHANNEL):
            if await _peer_allows_spam_blocked_send(peer, user.id):
                return

        if reply_to_message_id is not None and await _reply_to_incoming_message(
                peer, user.id, reply_to_message_id,
        ):
            return

    raise_spam_blocked_send_error()