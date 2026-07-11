from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class ForumTopicReadState(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User")
    topic: models.ForumTopic = fields.ForeignKeyField("models.ForumTopic")
    last_message_id: int = fields.BigIntField(default=0)

    user_id: int
    topic_id: int

    class Meta:
        unique_together = (
            ("user_id", "topic_id"),
        )