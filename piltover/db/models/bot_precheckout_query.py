from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class BotPrecheckoutQuery(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User", related_name="bot_precheckout_queries")
    bot: models.User = fields.ForeignKeyField("models.User", related_name="bot_precheckout_queries_received")
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    payload: bytes = fields.BinaryField()
    currency: str = fields.CharField(max_length=8)
    total_amount: int = fields.BigIntField()

    user_id: int
    bot_id: int