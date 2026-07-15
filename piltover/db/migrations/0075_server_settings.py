from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0074_bot_info_settings')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ServerSettings',
            fields=[
                ('id', fields.IntField(primary_key=True, default=1)),
                ('reports_enabled', fields.BooleanField(default=True)),
                ('bot_creation_enabled', fields.BooleanField(default=True)),
                ('group_creation_enabled', fields.BooleanField(default=True)),
                ('channel_creation_enabled', fields.BooleanField(default=True)),
                ('phone_calls_enabled', fields.BooleanField(default=True)),
            ],
            options={'table': 'serversettings', 'app': 'models', 'pk_attr': 'id'},
        ),
    ]