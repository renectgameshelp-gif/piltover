from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0060_user_stars')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='forum',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='Channel',
            name='next_topic_id',
            field=fields.IntField(default=2),
        ),
        ops.AddField(
            model_name='Dialog',
            name='view_forum_as_messages',
            field=fields.BooleanField(default=False),
        ),
        ops.CreateModel(
            name='ForumTopic',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('topic_id', fields.IntField()),
                ('title', fields.CharField(max_length=128)),
                ('icon_color', fields.IntField()),
                ('icon_emoji_id', fields.BigIntField(null=True, default=None)),
                ('closed', fields.BooleanField(default=False)),
                ('pinned', fields.BooleanField(default=False)),
                ('hidden', fields.BooleanField(default=False)),
                ('pinned_index', fields.IntField(null=True, default=None)),
                ('deleted', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
                ('channel', fields.ForeignKeyField('models.Channel', related_name='forum_topics', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('top_message', fields.ForeignKeyField('models.MessageRef', related_name='forum_topic_anchor', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('creator', fields.ForeignKeyField('models.User', related_name='created_forum_topics', db_constraint=True, on_delete=OnDelete.CASCADE)),
            ],
            options={
                'unique_together': (('channel_id', 'topic_id'),),
                'indexes': (('channel_id', 'deleted', 'topic_id'), ('channel_id', 'deleted', 'pinned_index')),
            },
        ),
        ops.CreateModel(
            name='ForumTopicReadState',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('last_message_id', fields.BigIntField(default=0)),
                ('user', fields.ForeignKeyField('models.User', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('topic', fields.ForeignKeyField('models.ForumTopic', db_constraint=True, on_delete=OnDelete.CASCADE)),
            ],
            options={
                'unique_together': (('user_id', 'topic_id'),),
            },
        ),
    ]