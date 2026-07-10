from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops

from piltover.db.enums import StarsPaymentPurpose, StarsTransactionPeerType


class Migration(migrations.Migration):
    dependencies = [('models', '0059_auto_20260703_1326')]

    initial = False

    operations = [
        ops.CreateModel(
            name='UserStarsBalance',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.OneToOneField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('amount', fields.BigIntField(default=0)),
                ('nanos', fields.IntField(default=0)),
            ],
            options={'table': 'userstarsbalance', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='StarsTransaction',
            fields=[
                ('transaction_id', fields.CharField(max_length=64, pk=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('stars_amount', fields.BigIntField()),
                ('stars_nanos', fields.IntField(default=0)),
                ('inbound', fields.BooleanField()),
                ('date', fields.IntField()),
                ('peer_type', fields.IntEnumField(description='', enum_type=StarsTransactionPeerType, generated=False)),
                ('peer_user', fields.ForeignKeyField('models.User', source_field='peer_user_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.SET_NULL, related_name='stars_transactions_as_peer')),
                ('title', fields.CharField(max_length=256, null=True)),
                ('description', fields.CharField(max_length=512, null=True)),
                ('gift', fields.BooleanField(default=False)),
                ('refund', fields.BooleanField(default=False)),
            ],
            options={'table': 'starstransaction', 'app': 'models', 'pk_attr': 'transaction_id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='StarsPaymentForm',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE)),
                ('purpose', fields.IntEnumField(description='', enum_type=StarsPaymentPurpose, generated=False)),
                ('stars', fields.BigIntField()),
                ('currency', fields.CharField(max_length=8)),
                ('amount', fields.BigIntField()),
                ('gift_user', fields.ForeignKeyField('models.User', source_field='gift_user_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.SET_NULL, related_name='stars_gift_forms')),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
                ('expires_at', fields.DatetimeField()),
            ],
            options={'table': 'starspaymentform', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]