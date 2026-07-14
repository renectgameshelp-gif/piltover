from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0067_verified_badge')]

    initial = False

    operations = [
        ops.AddField(
            model_name='User',
            name='admin',
            field=fields.BooleanField(default=False),
        ),
    ]