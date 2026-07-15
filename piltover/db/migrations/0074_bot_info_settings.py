from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0073_deleted_account_snapshot')]

    initial = False

    operations = [
        ops.AddField(
            model_name='BotInfo',
            name='inline_mode',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='BotInfo',
            name='can_join_groups',
            field=fields.BooleanField(default=True),
        ),
        ops.AddField(
            model_name='BotInfo',
            name='group_privacy',
            field=fields.BooleanField(default=True),
        ),
        ops.AddField(
            model_name='BotInfo',
            name='group_admin_rights',
            field=fields.IntField(default=4104),
        ),
        ops.AddField(
            model_name='BotInfo',
            name='channel_admin_rights',
            field=fields.IntField(default=0),
        ),
    ]