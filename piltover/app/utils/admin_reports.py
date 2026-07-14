from __future__ import annotations

from dataclasses import dataclass

from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.system_notifications import send_official_notification_message
from piltover.db.enums import AdminReportPeerType, MediaType, MessageType
from piltover.db.models import AdminReport, Channel, Chat, MessageRef, User, Username
from piltover.tl import KeyboardButtonRow, KeyboardButtonUrl, ReplyInlineMarkup

_REASON_LABELS = {
    "spam": "Spam",
    "violence": "Violence",
    "pornography": "Pornography",
    "child_abuse": "Child abuse",
    "copyright": "Copyright",
    "scam_or_fraud": "Scam or fraud",
    "illegal_goods": "Illegal goods",
    "personal_data": "Personal data",
    "other": "Other",
}

_PEER_TYPE_LABELS = {
    AdminReportPeerType.USER: "User",
    AdminReportPeerType.CHAT: "Basic group",
    AdminReportPeerType.CHANNEL: "Channel / supergroup",
    AdminReportPeerType.MESSAGE: "Messages",
}

_MEDIA_LABELS = {
    MediaType.PHOTO: "Photo",
    MediaType.DOCUMENT: "Document",
    MediaType.POLL: "Poll",
    MediaType.CONTACT: "Contact",
    MediaType.GEOPOINT: "Location",
    MediaType.DICE: "Dice",
    MediaType.INVOICE: "Invoice",
}

_REPORT_NOTIFY = FormatableTextWithEntities(
    "**New report** #{report_id}\n"
    "Type: {peer_type_label}\n"
    "Reporter: {reporter_label}\n"
    "Target: {target_label}\n"
    "Reason: {reason_label}\n"
    "{comment_block}"
    "{messages_block}"
    "{message_content_block}",
)


def format_report_reason(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason.replace("_", " ").title())


def format_peer_type(peer_type: AdminReportPeerType) -> str:
    return _PEER_TYPE_LABELS.get(peer_type, peer_type.name.title())


def report_start_param(report_id: int) -> str:
    return f"report_{report_id}"


async def get_first_admin_id() -> int | None:
    ids = await User.filter(admin=True, bot=False, deleted=False).order_by("id").limit(1).values_list("id", flat=True)
    return ids[0] if ids else None


async def _admin_bot_username() -> str | None:
    return await Username.filter(user_id__isnull=False, username__iexact="admin").first().values_list("username", flat=True)


@dataclass(frozen=True)
class ReportContext:
    target_user_id: int | None
    author_id: int | None
    target_is_bot: bool
    author_is_bot: bool


async def _resolve_message_ref(
        peer_type: AdminReportPeerType,
        peer_id: int,
        content_id: int,
        *,
        reporter_id: int | None = None,
) -> MessageRef | None:
    query = MessageRef.filter(content_id=content_id).select_related("content", "content__media")
    if peer_type is AdminReportPeerType.CHANNEL:
        return await query.filter(peer__channel_id=peer_id, peer__channel__deleted=False).first()
    if peer_type is AdminReportPeerType.CHAT:
        q = query.filter(peer__chat_id=peer_id, peer__chat__deleted=False, peer__chat__migrated=False)
        if reporter_id is not None:
            q = q.filter(peer__owner_id=reporter_id)
        return await q.first()
    if peer_type is AdminReportPeerType.USER:
        q = query.filter(peer__user_id=peer_id)
        if reporter_id is not None:
            q = q.filter(peer__owner_id=reporter_id)
        return await q.first()
    return None


def _snapshot_from_ref(ref: MessageRef) -> dict:
    content = ref.content
    media = None
    if content.media_id is not None and content.media is not None:
        media = _MEDIA_LABELS.get(content.media.type, "Media")
    msg_type = "service" if content.type not in (MessageType.REGULAR, MessageType.SCHEDULED) else "regular"
    return {
        "content_id": ref.content_id,
        "text": content.message,
        "media": media,
        "msg_type": msg_type,
        "date": content.date.isoformat() if content.date else None,
        "author_id": content.author_id,
    }


async def fetch_message_snapshots(
        peer_type: AdminReportPeerType,
        peer_id: int,
        message_ids: list[int],
        *,
        reporter_id: int | None = None,
) -> list[dict]:
    snapshots: list[dict] = []
    for content_id in message_ids:
        ref = await _resolve_message_ref(peer_type, peer_id, content_id, reporter_id=reporter_id)
        if ref is not None:
            snapshots.append(_snapshot_from_ref(ref))
        else:
            snapshots.append({"content_id": content_id, "text": None, "media": None, "missing": True})
    return snapshots


async def resolve_message_author(
        peer_type: AdminReportPeerType,
        peer_id: int,
        message_ids: list[int],
        *,
        reporter_id: int | None = None,
) -> int | None:
    if not message_ids:
        return None
    ref = await _resolve_message_ref(peer_type, peer_id, message_ids[0], reporter_id=reporter_id)
    return ref.content.author_id if ref else None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_snapshot_line(snap: dict, *, text_limit: int = 800) -> list[str]:
    content_id = snap.get("content_id", "?")
    if snap.get("missing"):
        return [f"  #{content_id}: message not found (deleted or unavailable)"]

    lines = [f"  #{content_id}:"]
    if snap.get("date"):
        lines[0] += f" ({snap['date'][:16].replace('T', ' ')})"

    if snap.get("msg_type") == "service":
        lines.append("    [service message]")
        return lines

    text = snap.get("text") or ""
    media = snap.get("media")
    if text:
        for line in _truncate(text, text_limit).splitlines() or [""]:
            lines.append(f"    {line}")
    if media:
        lines.append(f"    [{media}]")
    if not text and not media:
        lines.append("    (empty)")
    return lines


async def _report_message_snapshots(report: AdminReport) -> list[dict]:
    if report.message_snapshot:
        return report.message_snapshot
    if not report.message_ids:
        return []
    return await fetch_message_snapshots(
        report.peer_type,
        report.peer_id,
        report.message_ids,
        reporter_id=report.reporter_id,
    )


def _format_message_content_block(snapshots: list[dict], *, text_limit: int = 800) -> list[str]:
    if not snapshots:
        return []
    lines = ["", "Reported message(s):"]
    for snap in snapshots:
        lines.extend(_format_snapshot_line(snap, text_limit=text_limit))
    return lines


def _format_message_notify_block(snapshots: list[dict]) -> str:
    if not snapshots:
        return ""
    parts: list[str] = ["Message:\n"]
    for snap in snapshots:
        content_id = snap.get("content_id", "?")
        if snap.get("missing"):
            parts.append(f"#{content_id}: unavailable\n")
            continue
        if snap.get("msg_type") == "service":
            parts.append(f"#{content_id}: [service message]\n")
            continue
        text = snap.get("text") or ""
        media = snap.get("media")
        if text:
            parts.append(f"#{content_id}: {_truncate(text, 400)}\n")
        elif media:
            parts.append(f"#{content_id}: [{media}]\n")
        else:
            parts.append(f"#{content_id}: (empty)\n")
    return "".join(parts)


async def get_report_context(report: AdminReport) -> ReportContext:
    author_id = report.author_id
    if author_id is None and report.message_ids:
        author_id = await resolve_message_author(
            report.peer_type, report.peer_id, report.message_ids, reporter_id=report.reporter_id,
        )

    target_user_id = None
    target_is_bot = False
    if report.peer_type is AdminReportPeerType.USER:
        target_user_id = report.peer_id
        user = await User.get_or_none(id=target_user_id, deleted=False)
        if user is not None:
            target_is_bot = user.bot

    author_is_bot = False
    if author_id is not None:
        author = await User.get_or_none(id=author_id, deleted=False)
        if author is not None:
            author_is_bot = author.bot

    return ReportContext(
        target_user_id=target_user_id,
        author_id=author_id,
        target_is_bot=target_is_bot,
        author_is_bot=author_is_bot,
    )


async def _user_brief(user_id: int) -> str:
    user = await User.get_or_none(id=user_id)
    if user is None:
        return f"id {user_id}"
    username = await user.get_raw_username()
    name = user.first_name or "user"
    if user.last_name:
        name = f"{name} {user.last_name}"
    badges = []
    if user.bot:
        badges.append("🤖")
    if user.system:
        badges.append("⚙")
    if user.verified:
        badges.append("✓")
    badge = "".join(badges)
    prefix = f"{badge} " if badge else ""
    un = f" @{username}" if username else ""
    return f"{prefix}{name}{un} (id {user.id})"


async def describe_report_target(peer_type: AdminReportPeerType, peer_id: int) -> tuple[str, list[str]]:
    if peer_type is AdminReportPeerType.USER:
        user = await User.get_or_none(id=peer_id)
        if user is None:
            return f"User id {peer_id}", [f"User id: {peer_id}", "Status: not found"]
        username = await user.get_raw_username()
        lines = [
            f"User: {user.first_name}" + (f" {user.last_name}" if user.last_name else ""),
            f"User id: {user.id}",
        ]
        if username:
            lines.append(f"Username: @{username}")
        if user.bot:
            lines.append("Type: bot")
        if user.system:
            lines.append("Service account: yes")
        lines.append(f"Verified: {'yes' if user.verified else 'no'}")
        label = await _user_brief(peer_id)
        return label, lines

    if peer_type is AdminReportPeerType.CHANNEL:
        channel = await Channel.get_or_none(id=peer_id)
        if channel is None:
            return f"Channel id {peer_id}", [f"Channel id: {peer_id}", "Status: not found"]
        kind = "channel" if channel.channel else "supergroup"
        un = await Username.get_or_none(channel_id=channel.id)
        lines = [
            f"{kind.title()}: {channel.name}",
            f"DB id: {channel.id}",
            f"TL id: {channel.make_id()}",
            f"Members: {channel.participants_count}",
            f"Verified: {'yes' if channel.verified else 'no'}",
        ]
        if un:
            lines.append(f"Username: @{un.username}")
        label = f"@{un.username}" if un else channel.name
        return label, lines

    if peer_type is AdminReportPeerType.CHAT:
        chat = await Chat.get_or_none(id=peer_id)
        if chat is None:
            return f"Group id {peer_id}", [f"Group id: {peer_id}", "Status: not found"]
        lines = [
            f"Group: {chat.name}",
            f"DB id: {chat.id}",
            f"TL id: {chat.make_id()}",
            f"Members: {chat.participants_count}",
            f"Verified: {'yes' if chat.verified else 'no'}",
        ]
        return chat.name, lines

    return f"messages {peer_id}", [f"Message ids context: {peer_id}"]


async def build_report_detail_lines(report: AdminReport) -> list[str]:
    ctx = await get_report_context(report)
    reporter_label = await _user_brief(report.reporter_id)
    target_label, target_lines = await describe_report_target(report.peer_type, report.peer_id)
    created = report.created_at.strftime("%Y-%m-%d %H:%M UTC") if report.created_at else "—"

    lines = [
        f"📩 Report #{report.id}",
        f"Status: {'reviewed ✓' if report.reviewed else 'pending •'}",
        f"Created: {created}",
        "",
        "Reporter:",
        f"  {reporter_label}",
        "",
        f"Target ({format_peer_type(report.peer_type)}):",
        f"  {target_label}",
    ]
    for line in target_lines:
        lines.append(f"  {line}")
    if ctx.author_id is not None and (
            report.message_ids
            or ctx.author_id != report.peer_id
    ):
        lines.extend(["", "Message author:", f"  {await _user_brief(ctx.author_id)}"])
    lines.extend([
        "",
        f"Reason: {format_report_reason(report.reason)}",
    ])
    if report.comment:
        lines.extend(["", "Comment:", report.comment[:500]])
    snapshots = await _report_message_snapshots(report)
    lines.extend(_format_message_content_block(snapshots))
    return lines


async def create_admin_report(
        *,
        reporter_id: int,
        peer_type: AdminReportPeerType,
        peer_id: int,
        reason: str,
        comment: str | None = None,
        message_ids: list[int] | None = None,
        author_id: int | None = None,
        message_snapshot: list[dict] | None = None,
) -> AdminReport:
    if message_ids and message_snapshot is None:
        message_snapshot = await fetch_message_snapshots(
            peer_type, peer_id, message_ids, reporter_id=reporter_id,
        )
    if author_id is None and message_snapshot:
        for snap in message_snapshot:
            if snap.get("author_id"):
                author_id = snap["author_id"]
                break
    if author_id is None and message_ids:
        author_id = await resolve_message_author(
            peer_type, peer_id, message_ids, reporter_id=reporter_id,
        )

    report = await AdminReport.create(
        reporter_id=reporter_id,
        peer_type=peer_type,
        peer_id=peer_id,
        reason=reason,
        comment=comment,
        message_ids=message_ids,
        message_snapshot=message_snapshot,
        author_id=author_id,
    )
    await notify_first_admin(report)
    return report


async def notify_first_admin(report: AdminReport) -> None:
    admin_id = await get_first_admin_id()
    if admin_id is None:
        return

    ctx = await get_report_context(report)
    reporter_label = await _user_brief(report.reporter_id)
    target_label, _ = await describe_report_target(report.peer_type, report.peer_id)
    comment_block = f"Comment:\n{report.comment}\n\n" if report.comment else ""
    snapshots = report.message_snapshot or []
    messages_block = ""
    if ctx.author_id is not None and (
            report.message_ids or ctx.author_id != report.peer_id
    ):
        author_label = await _user_brief(ctx.author_id)
        messages_block = f"Author: {author_label}\n"
    message_content_block = _format_message_notify_block(snapshots)

    text, entities = _REPORT_NOTIFY.format(
        report_id=report.id,
        peer_type_label=format_peer_type(report.peer_type),
        reporter_label=reporter_label,
        target_label=target_label,
        reason_label=format_report_reason(report.reason),
        comment_block=comment_block,
        messages_block=messages_block,
        message_content_block=message_content_block,
    )

    reply_markup = None
    admin_username = await _admin_bot_username()
    if admin_username:
        reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonUrl(
                    text="Open in @admin",
                    url=f"https://t.me/{admin_username}?start={report_start_param(report.id)}",
                ),
            ]),
        ])

    await send_official_notification_message(admin_id, text, entities, reply_markup=reply_markup)