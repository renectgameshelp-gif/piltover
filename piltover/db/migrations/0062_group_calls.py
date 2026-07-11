from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0061_forum_topics')]

    initial = False

    operations = [
        ops.CreateModel(
            name='GroupCall',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('access_hash', fields.BigIntField()),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
                ('started_at', fields.DatetimeField(null=True, default=None)),
                ('discarded_at', fields.DatetimeField(null=True, default=None)),
                ('title', fields.CharField(max_length=128, null=True, default=None)),
                ('join_muted', fields.BooleanField(default=True)),
                ('can_change_join_muted', fields.BooleanField(default=True)),
                ('schedule_date', fields.DatetimeField(null=True, default=None)),
                ('version', fields.IntField(default=1)),
                ('participants_version', fields.IntField(default=1)),
                ('next_source', fields.IntField(default=1)),
                ('invite_hash', fields.CharField(max_length=32, null=True, default=None)),
                ('creator', fields.ForeignKeyField('models.User', related_name='created_group_calls', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('chat', fields.ForeignKeyField('models.Chat', null=True, default=None, related_name='group_calls', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('channel', fields.ForeignKeyField('models.Channel', null=True, default=None, related_name='group_calls', db_constraint=True, on_delete=OnDelete.CASCADE)),
            ],
        ),
        ops.CreateModel(
            name='GroupCallParticipant',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('source', fields.IntField()),
                ('muted', fields.BooleanField(default=True)),
                ('video_stopped', fields.BooleanField(default=True)),
                ('left', fields.BooleanField(default=False)),
                ('joined_at', fields.DatetimeField(auto_now_add=True)),
                ('group_call', fields.ForeignKeyField('models.GroupCall', related_name='participants', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('user', fields.ForeignKeyField('models.User', related_name='group_call_participations', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('join_as_user', fields.ForeignKeyField('models.User', null=True, default=None, related_name='group_call_join_as_participations', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('join_as_channel', fields.ForeignKeyField('models.Channel', null=True, default=None, related_name='group_call_join_as_participations', db_constraint=True, on_delete=OnDelete.CASCADE)),
            ],
            options={
                'unique_together': (('group_call_id', 'user_id'), ('group_call_id', 'source')),
            },
        ),
        ops.CreateModel(
            name='DefaultGroupCallJoinAs',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('user', fields.ForeignKeyField('models.User', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('chat', fields.ForeignKeyField('models.Chat', null=True, default=None, db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('channel', fields.ForeignKeyField('models.Channel', null=True, default=None, db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('join_as_user', fields.ForeignKeyField('models.User', null=True, default=None, related_name='default_group_call_join_as_user', db_constraint=True, on_delete=OnDelete.CASCADE)),
                ('join_as_channel', fields.ForeignKeyField('models.Channel', null=True, default=None, related_name='default_group_call_join_as_channel', db_constraint=True, on_delete=OnDelete.CASCADE)),
            ],
            options={
                'unique_together': (('user_id', 'chat_id'), ('user_id', 'channel_id')),
            },
        ),
    ]