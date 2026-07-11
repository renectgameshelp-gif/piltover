from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0063_group_call_participant_flags')]

    initial = False

    operations = [
        ops.AddField(
            model_name='GroupCallParticipant',
            name='volume',
            field=fields.IntField(default=10000),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='volume_by_admin',
            field=fields.BooleanField(default=False),
        ),
        ops.AlterField(
            model_name='GroupCall',
            name='join_muted',
            field=fields.BooleanField(default=False),
        ),
        ops.RunSQL(
            "UPDATE `groupcall` SET `join_muted` = 0 WHERE `discarded_at` IS NULL",
            reverse_sql="UPDATE `groupcall` SET `join_muted` = 1 WHERE `discarded_at` IS NULL",
        ),
    ]