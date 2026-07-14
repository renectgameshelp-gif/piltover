from orjson import loads
from tortoise import fields
from tortoise import migrations
from tortoise.fields.data import JSON_DUMPS
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0071_admin_report_author')]

    initial = False

    operations = [
        ops.AddField(
            model_name='AdminReport',
            name='message_snapshot',
            field=fields.JSONField(null=True, default=None, encoder=JSON_DUMPS, decoder=loads),
        ),
    ]