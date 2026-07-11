from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class ForumTopic(Model):
    id: int = fields.BigIntField(primary_key=True)
    topic_id: int = fields.IntField()
    channel: models.Channel = fields.ForeignKeyField("models.Channel", related_name="forum_topics")
    top_message: models.MessageRef = fields.ForeignKeyField("models.MessageRef", related_name="forum_topic_anchor")
    title: str = fields.CharField(max_length=128)
    icon_color: int = fields.IntField()
    icon_emoji_id: int | None = fields.BigIntField(null=True, default=None)
    creator: models.User = fields.ForeignKeyField("models.User", related_name="created_forum_topics")
    closed: bool = fields.BooleanField(default=False)
    pinned: bool = fields.BooleanField(default=False)
    hidden: bool = fields.BooleanField(default=False)
    pinned_index: int | None = fields.IntField(null=True, default=None)
    deleted: bool = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    channel_id: int
    top_message_id: int
    creator_id: int

    class Meta:
        unique_together = (
            ("channel_id", "topic_id"),
        )
        indexes = (
            ("channel_id", "deleted", "topic_id"),
            ("channel_id", "deleted", "pinned_index"),
        )