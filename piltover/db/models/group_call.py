from __future__ import annotations

from datetime import datetime

from piltover.utils.fastrand_shim import xorshift128plus_bytes
from tortoise import Model, fields

from piltover.db import models
from piltover.tl import GroupCall as TLGroupCall, GroupCallDiscarded, InputGroupCall, Long


def group_call_gen_access_hash() -> int:
    return Long.read_bytes(xorshift128plus_bytes(8), signed=True)


class GroupCall(Model):
    id: int = fields.BigIntField(primary_key=True)
    access_hash: int = fields.BigIntField(default=group_call_gen_access_hash)
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    started_at: datetime | None = fields.DatetimeField(null=True, default=None)
    discarded_at: datetime | None = fields.DatetimeField(null=True, default=None)
    title: str | None = fields.CharField(max_length=128, null=True, default=None)
    join_muted: bool = fields.BooleanField(default=False)
    can_change_join_muted: bool = fields.BooleanField(default=True)
    schedule_date: datetime | None = fields.DatetimeField(null=True, default=None)
    version: int = fields.IntField(default=1)
    participants_version: int = fields.IntField(default=1)
    next_source: int = fields.IntField(default=1)
    invite_hash: str | None = fields.CharField(max_length=32, null=True, default=None)
    creator: models.User = fields.ForeignKeyField("models.User", related_name="created_group_calls")
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None, related_name="group_calls")
    channel: models.Channel | None = fields.ForeignKeyField(
        "models.Channel", null=True, default=None, related_name="group_calls",
    )

    creator_id: int
    chat_id: int | None
    channel_id: int | None

    @property
    def is_active(self) -> bool:
        return self.discarded_at is None and self.started_at is not None

    @property
    def is_scheduled(self) -> bool:
        return self.discarded_at is None and self.started_at is None and self.schedule_date is not None

    def to_input(self) -> InputGroupCall:
        return InputGroupCall(id=self.id, access_hash=self.access_hash)

    async def participants_count(self) -> int:
        return await models.GroupCallParticipant.filter(group_call=self, left=False).count()

    async def bump_participants_version(self) -> None:
        self.version += 1
        self.participants_version = self.version
        await self.save(update_fields=["version", "participants_version"])

    async def to_tl(self, *, participants_count: int | None = None) -> TLGroupCall | GroupCallDiscarded:
        if self.discarded_at is not None:
            duration = 0
            if self.started_at is not None:
                duration = int((self.discarded_at - self.started_at).total_seconds())
            return GroupCallDiscarded(id=self.id, access_hash=self.access_hash, duration=duration)

        if participants_count is None:
            participants_count = await self.participants_count()
        schedule_date = int(self.schedule_date.timestamp()) if self.schedule_date is not None else None

        return TLGroupCall(
            join_muted=self.join_muted,
            can_change_join_muted=self.can_change_join_muted,
            join_date_asc=True,
            can_start_video=True,
            id=self.id,
            access_hash=self.access_hash,
            participants_count=participants_count,
            title=self.title,
            schedule_date=schedule_date,
            unmuted_video_limit=30,
            version=self.version,
        )

    @classmethod
    async def get_from_input(cls, call: InputGroupCall) -> GroupCall | None:
        return await cls.get_or_none(id=call.id, access_hash=call.access_hash, discarded_at__isnull=True)

    @classmethod
    async def get_from_input_any(cls, call: InputGroupCall) -> GroupCall | None:
        return await cls.get_or_none(id=call.id, access_hash=call.access_hash)

    @classmethod
    async def get_from_input_raise(cls, call: InputGroupCall) -> GroupCall:
        from piltover.exceptions import ErrorRpc

        group_call = await cls.get_from_input_any(call)
        if group_call is None:
            raise ErrorRpc(error_code=400, error_message="GROUPCALL_INVALID")
        if group_call.discarded_at is not None:
            raise ErrorRpc(error_code=403, error_message="GROUPCALL_FORBIDDEN")
        return group_call

    @classmethod
    async def get_active_for_chat(cls, chat: models.Chat) -> GroupCall | None:
        return await cls.get_or_none(chat=chat, discarded_at__isnull=True)

    @classmethod
    async def get_active_for_channel(cls, channel: models.Channel) -> GroupCall | None:
        return await cls.get_or_none(channel=channel, discarded_at__isnull=True)