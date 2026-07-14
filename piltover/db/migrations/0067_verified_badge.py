from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0066_message_ref_discussion_top')]

    initial = False

    operations = [
        ops.AddField(
            model_name='User',
            name='verified',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='Chat',
            name='verified',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='Channel',
            name='verified',
            field=fields.BooleanField(default=False),
        ),
    ]