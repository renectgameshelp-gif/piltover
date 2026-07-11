from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields, Model
from tortoise.exceptions import IntegrityError

from piltover.auth_data import AuthData


async def _create_ignore_asyncmy_overflow(model: type[Model], **kwargs) -> Model:
    try:
        return await model.create(**kwargs)
    except (OverflowError, IntegrityError):
        # asyncmy on Windows may raise OverflowError while parsing the OK packet
        # even though the INSERT succeeded (insert_id > 32-bit unsigned long).
        instance = await model.get_or_none(id=kwargs["id"])
        if instance is None:
            raise
        if "auth_key" in kwargs and getattr(instance, "auth_key", None) != kwargs["auth_key"]:
            raise
        return instance


class AuthKey(Model):
    id: int = fields.BigIntField(primary_key=True)
    auth_key: bytes = fields.BinaryField()
    layer: int = fields.SmallIntField(default=133)

    @classmethod
    async def get_temp_id(cls, key_id: int) -> int | None:
        return cast(int | None, await TempAuthKey.filter(perm_key_id=key_id).first().values_list("id", flat=True))

    @classmethod
    async def get_temp_ids_bulk(cls, key_ids: list[int]) -> list[int]:
        return cast(list[int], await TempAuthKey.filter(perm_key_id__in=key_ids).values_list("id", flat=True))

    @classmethod
    async def create_key(cls, id: int, auth_key: bytes) -> AuthKey:
        return cast(AuthKey, await _create_ignore_asyncmy_overflow(cls, id=id, auth_key=auth_key))

    @classmethod
    async def is_registered(cls, key_id: int) -> bool:
        return await cls.get_auth_data(key_id) is not None

    @classmethod
    async def can_bind_temp_auth_key(cls, temp_key_id: int, perm_key_id: int) -> bool:
        if await TempAuthKey.get_or_none(id=temp_key_id, expires_at__gt=int(time())) is None:
            return False
        return await cls.get_or_none(id=perm_key_id) is not None

    @classmethod
    async def get_auth_data(cls, key_id: int, *, allow_expired: bool = False) -> AuthData | None:
        if (key := await AuthKey.get_or_none(id=key_id)) is not None:
            return AuthData(
                auth_key_id=key.id,
                auth_key=key.auth_key,
                perm_auth_key_id=key.id,
            )

        temp_query = TempAuthKey.filter(id=key_id)
        if not allow_expired:
            temp_query = temp_query.filter(expires_at__gt=int(time()))
        temp_key = await temp_query.first()
        if temp_key is None:
            return None
        return AuthData(
            auth_key_id=temp_key.id,
            auth_key=temp_key.auth_key,
            perm_auth_key_id=temp_key.perm_key_id,
        )


class TempAuthKey(Model):
    id: int = fields.BigIntField(primary_key=True)
    auth_key: bytes = fields.BinaryField()
    expires_at: int = fields.BigIntField()
    perm_key: AuthKey | None = fields.OneToOneField("models.AuthKey", null=True)

    perm_key_id: int | None

    @classmethod
    async def create_key(cls, id: int, auth_key: bytes, expires_at: int) -> TempAuthKey:
        return cast(
            TempAuthKey,
            await _create_ignore_asyncmy_overflow(cls, id=id, auth_key=auth_key, expires_at=expires_at),
        )
