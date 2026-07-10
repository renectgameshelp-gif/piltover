from __future__ import annotations

from datetime import datetime, timedelta, UTC

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import StarsPaymentPurpose
from piltover.utils.snowflake import Snowflake


class StarsPaymentForm(Model):
    FORM_TTL_SECONDS = 30 * 60

    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User", related_name="stars_payment_forms")
    purpose: StarsPaymentPurpose = fields.IntEnumField(StarsPaymentPurpose)
    stars: int = fields.BigIntField()
    currency: str = fields.CharField(max_length=8)
    amount: int = fields.BigIntField()
    gift_user: models.User | None = fields.ForeignKeyField(
        "models.User", null=True, default=None, related_name="stars_gift_forms",
    )
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    expires_at: datetime = fields.DatetimeField()

    user_id: int
    gift_user_id: int | None

    @classmethod
    def gen_expires_at(cls) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=cls.FORM_TTL_SECONDS)

    @classmethod
    async def create_form(
            cls, user_id: int, purpose: StarsPaymentPurpose, stars: int, currency: str, amount: int,
            gift_user_id: int | None = None,
    ) -> StarsPaymentForm:
        return await cls.create(
            id=Snowflake.make_id(),
            user_id=user_id,
            purpose=purpose,
            stars=stars,
            currency=currency,
            amount=amount,
            gift_user_id=gift_user_id,
            expires_at=cls.gen_expires_at(),
        )

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at