from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0070_admin_panel_extras')]

    initial = False

    operations = [
        ops.AddField(
            model_name='AdminReport',
            name='author_id',
            field=fields.BigIntField(null=True, default=None),
        ),
    ]