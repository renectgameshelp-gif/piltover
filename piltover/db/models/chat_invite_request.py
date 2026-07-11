from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from tortoise import Model, fields

from piltover.db import models

if TYPE_CHECKING:
    from piltover.db.models.chat_base import ChatBase


class ChatInviteRequest(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User")
    invite: models.ChatInvite = fields.ForeignKeyField("models.ChatInvite")
    created_at: datetime = fields.DatetimeField(auto_now_add=True)

    user_id: int | None
    invite_id: int | None

    @classmethod
    async def delete_by_invite_ids(cls, invite_ids: list[int] | set[int], **filters) -> None:
        if not invite_ids:
            return
        await cls.filter(invite_id__in=invite_ids, **filters).delete()

    @classmethod
    async def delete_for_chat(cls, chat: models.Chat | int, **filters) -> None:
        chat_id = chat.id if isinstance(chat, models.Chat) else chat
        invite_ids = await models.ChatInvite.filter(chat_id=chat_id).values_list("id", flat=True)
        await cls.delete_by_invite_ids(invite_ids, **filters)

    @classmethod
    async def delete_for_channel(cls, channel: models.Channel | int, **filters) -> None:
        channel_id = channel.id if isinstance(channel, models.Channel) else channel
        invite_ids = await models.ChatInvite.filter(channel_id=channel_id).values_list("id", flat=True)
        await cls.delete_by_invite_ids(invite_ids, **filters)

    @classmethod
    async def delete_for_chat_or_channel(cls, chat_or_channel: ChatBase, **filters) -> None:
        if isinstance(chat_or_channel, models.Chat):
            await cls.delete_for_chat(chat_or_channel, **filters)
        elif isinstance(chat_or_channel, models.Channel):
            await cls.delete_for_channel(chat_or_channel, **filters)
        else:
            raise NotImplementedError