from __future__ import annotations

from tortoise import fields, Model


class BlockedPhone(Model):
    id: int = fields.BigIntField(primary_key=True)
    phone_number: str = fields.CharField(max_length=20, unique=True)
    user_id: int | None = fields.BigIntField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True)