from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0064_group_call_participant_volume')]

    initial = False

    operations = [
        ops.AddField(
            model_name='StarsTransaction',
            name='msg_id',
            field=fields.IntField(null=True),
        ),
        ops.AddField(
            model_name='StarsTransaction',
            name='bot_payload',
            field=fields.BinaryField(null=True),
        ),
        ops.AddField(
            model_name='StarsPaymentForm',
            name='bot_user',
            field=fields.ForeignKeyField(
                'models.User', source_field='bot_user_id', null=True, db_constraint=True,
                to_field='id', on_delete=OnDelete.SET_NULL, related_name='stars_bot_invoice_forms',
            ),
        ),
        ops.AddField(
            model_name='StarsPaymentForm',
            name='message_id',
            field=fields.IntField(null=True),
        ),
        ops.AddField(
            model_name='StarsPaymentForm',
            name='payload',
            field=fields.BinaryField(null=True),
        ),
        ops.CreateModel(
            name='BotPrecheckoutQuery',
            fields=[
                ('id', fields.BigIntField(primary_key=True)),
                ('user', fields.ForeignKeyField(
                    'models.User', source_field='user_id', db_constraint=True, to_field='id',
                    on_delete=OnDelete.CASCADE, related_name='bot_precheckout_queries',
                )),
                ('bot', fields.ForeignKeyField(
                    'models.User', source_field='bot_id', db_constraint=True, to_field='id',
                    on_delete=OnDelete.CASCADE, related_name='bot_precheckout_queries_received',
                )),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
                ('payload', fields.BinaryField()),
                ('currency', fields.CharField(max_length=8)),
                ('total_amount', fields.BigIntField()),
            ],
            options={'table': 'botprecheckoutquery', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]