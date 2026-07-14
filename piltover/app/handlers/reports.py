from __future__ import annotations

from piltover.db.enums import AdminReportPeerType, PeerType
from piltover.db.models import Peer
from piltover.enums import ReqHandlerFlags
from piltover.tl.functions.account import ReportPeer, ReportProfilePhoto
from piltover.worker import MessageHandler

handler = MessageHandler("reports")


def _reason_name(reason) -> str:
    return type(reason).__name__.replace("InputReportReason", "").lower() or "other"


@handler.on_request(ReportPeer, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def report_peer(request: ReportPeer, user_id: int) -> bool:
    from piltover.app.utils.admin_reports import create_admin_report

    peer = await Peer.from_input_peer_raise(user_id, request.peer)
    if peer.type is PeerType.USER:
        peer_type = AdminReportPeerType.USER
        peer_id = peer.user_id
    elif peer.type is PeerType.CHAT:
        peer_type = AdminReportPeerType.CHAT
        peer_id = peer.chat_id
    elif peer.type is PeerType.CHANNEL:
        peer_type = AdminReportPeerType.CHANNEL
        peer_id = peer.channel_id
    else:
        return True

    await create_admin_report(
        reporter_id=user_id,
        peer_type=peer_type,
        peer_id=peer_id,
        reason=_reason_name(request.reason),
        comment=request.message or None,
    )
    return True


@handler.on_request(ReportProfilePhoto, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def report_profile_photo(request: ReportProfilePhoto, user_id: int) -> bool:
    from piltover.app.utils.admin_reports import create_admin_report

    peer = await Peer.from_input_peer_raise(user_id, request.peer)
    if peer.type is not PeerType.USER:
        return True

    await create_admin_report(
        reporter_id=user_id,
        peer_type=AdminReportPeerType.USER,
        peer_id=peer.user_id,
        reason=_reason_name(request.reason),
        comment=request.message or None,
    )
    return True