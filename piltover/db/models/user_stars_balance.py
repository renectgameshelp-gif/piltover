from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import StarsAmount


class UserStarsBalance(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User", related_name="stars_balance")
    amount: int = fields.BigIntField(default=0)
    nanos: int = fields.IntField(default=0)

    user_id: int

    def to_stars_amount(self) -> StarsAmount:
        return StarsAmount(amount=self.amount, nanos=self.nanos)

    @classmethod
    async def get_or_create_for(cls, user_id: int) -> UserStarsBalance:
        balance, _ = await cls.get_or_create(user_id=user_id, defaults={"amount": 0, "nanos": 0})
        return balance