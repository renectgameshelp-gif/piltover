from __future__ import annotations

from tortoise import Model, fields


class DeletedAccountSnapshot(Model):
    user_id: int = fields.BigIntField(primary_key=True)
    phone_number: str | None = fields.CharField(max_length=20, null=True, default=None)
    first_name: str = fields.CharField(max_length=64)
    last_name: str | None = fields.CharField(max_length=64, null=True, default=None)
    about: str | None = fields.TextField(null=True, default=None)
    bot: bool = fields.BooleanField(default=False)
    username: str | None = fields.CharField(max_length=32, null=True, default=None)
    bot_owner_id: int | None = fields.BigIntField(null=True, default=None)
    bot_token_nonce: str | None = fields.CharField(max_length=36, null=True, default=None)
    verified: bool = fields.BooleanField(default=False)
    admin: bool = fields.BooleanField(default=False)
    spam_blocked: bool = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)