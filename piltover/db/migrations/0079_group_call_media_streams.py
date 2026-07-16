from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0078_user_support')]

    initial = False

    operations = [
        ops.AddField(
            model_name='GroupCallParticipant',
            name='video_source',
            field=fields.IntField(null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='presentation_source',
            field=fields.IntField(null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='video_endpoint',
            field=fields.CharField(max_length=256, null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='presentation_endpoint',
            field=fields.CharField(max_length=256, null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='video_source_groups',
            field=fields.JSONField(null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='presentation_source_groups',
            field=fields.JSONField(null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='video_paused',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='presentation_paused',
            field=fields.BooleanField(default=False),
        ),
    ]