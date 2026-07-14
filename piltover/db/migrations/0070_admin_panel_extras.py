from orjson import loads
from tortoise import fields
from tortoise import migrations
from tortoise.fields.data import JSON_DUMPS
from tortoise.migrations import operations as ops

from piltover.db.enums import AdminReportPeerType


class Migration(migrations.Migration):
    dependencies = [('models', '0069_user_spam_blocked')]

    initial = False

    operations = [
        ops.CreateModel(
            name='BlockedPhone',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('phone_number', fields.CharField(max_length=20, unique=True)),
                ('user_id', fields.BigIntField(null=True, default=None)),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
            ],
            options={'table': 'blockedphone', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='AdminReport',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('reporter_id', fields.BigIntField()),
                ('peer_type', fields.IntEnumField(description='', enum_type=AdminReportPeerType, generated=False)),
                ('peer_id', fields.BigIntField()),
                ('reason', fields.CharField(max_length=64, default='other')),
                ('comment', fields.TextField(null=True, default=None)),
                ('message_ids', fields.JSONField(null=True, default=None, encoder=JSON_DUMPS, decoder=loads)),
                ('reviewed', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
            ],
            options={'table': 'adminreport', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]