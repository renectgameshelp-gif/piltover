from __future__ import annotations

from tortoise import Model, fields

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import ChatAdminRights
from piltover.tl.types import BotInfo as TLBotInfo

_DEFAULT_GROUP_ADMIN_RIGHTS = ChatAdminRights.DELETE_MESSAGES | ChatAdminRights.OTHER


class BotInfo(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.OneToOneField("models.User", related_name="bot_info")
    description: str | None = fields.CharField(max_length=128, null=True, default=None)
    description_photo: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    # TODO: description_document
    privacy_policy_url: str | None = fields.CharField(max_length=240, null=True, default=None)
    inline_mode: bool = fields.BooleanField(default=False)
    can_join_groups: bool = fields.BooleanField(default=True)
    group_privacy: bool = fields.BooleanField(default=True)
    group_admin_rights: int = fields.IntField(default=_DEFAULT_GROUP_ADMIN_RIGHTS)
    channel_admin_rights: int = fields.IntField(default=0)
    version: int = fields.IntField(default=1)

    user_id: int
    description_photo_id: int | None

    def _cache_key(self) -> str:
        return f"bot-info:{self.user_id}:{self.version}"

    @classmethod
    async def get_or_create_for_bot(cls, bot_id: int) -> BotInfo:
        info, _ = await cls.get_or_create(
            user_id=bot_id,
            defaults={
                "group_admin_rights": _DEFAULT_GROUP_ADMIN_RIGHTS,
            },
        )
        return info

    async def to_tl(self) -> TLBotInfo:
        if (cached := await Cache.obj.get(self._cache_key())) is not None:
            return cached

        commands = await models.BotCommand.filter(bot_id=self.user_id)

        result = TLBotInfo(
            user_id=self.user_id,
            description=self.description,
            description_photo=self.description_photo.to_tl_photo() if self.description_photo_id is not None else None,
            commands=[
                command.to_tl()
                for command in commands
            ],
            privacy_policy_url=self.privacy_policy_url,
        )

        await Cache.obj.set(self._cache_key(), result)
        return result
