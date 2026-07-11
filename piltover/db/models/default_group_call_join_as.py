from tortoise import Model, fields

from piltover.db import models


class DefaultGroupCallJoinAs(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User")
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    join_as_user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None, related_name="default_group_call_join_as_user")
    join_as_channel: models.Channel | None = fields.ForeignKeyField(
        "models.Channel", null=True, default=None, related_name="default_group_call_join_as_channel",
    )

    user_id: int
    chat_id: int | None
    channel_id: int | None
    join_as_user_id: int | None
    join_as_channel_id: int | None