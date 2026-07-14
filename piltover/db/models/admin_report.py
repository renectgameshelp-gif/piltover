from __future__ import annotations

from tortoise import fields, Model

from piltover.db.enums import AdminReportPeerType


class AdminReport(Model):
    id: int = fields.BigIntField(primary_key=True)
    reporter_id: int = fields.BigIntField()
    peer_type: AdminReportPeerType = fields.IntEnumField(AdminReportPeerType)
    peer_id: int = fields.BigIntField()
    reason: str = fields.CharField(max_length=64, default="other")
    comment: str | None = fields.TextField(null=True, default=None)
    message_ids: list[int] | None = fields.JSONField(null=True, default=None)
    message_snapshot: list[dict] | None = fields.JSONField(null=True, default=None)
    author_id: int | None = fields.BigIntField(null=True, default=None)
    reviewed: bool = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)