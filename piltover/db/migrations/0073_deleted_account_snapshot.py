from tortoise import fields
from tortoise.migrations import Migration, operations as ops


class Migration(Migration):
    dependencies = [('models', '0072_admin_report_snapshot')]

    initial = False

    operations = [
        ops.CreateModel(
            name='DeletedAccountSnapshot',
            fields=[
                ('user_id', fields.BigIntField(primary_key=True)),
                ('phone_number', fields.CharField(max_length=20, null=True, default=None)),
                ('first_name', fields.CharField(max_length=64)),
                ('last_name', fields.CharField(max_length=64, null=True, default=None)),
                ('about', fields.TextField(null=True, default=None)),
                ('bot', fields.BooleanField(default=False)),
                ('username', fields.CharField(max_length=32, null=True, default=None)),
                ('bot_owner_id', fields.BigIntField(null=True, default=None)),
                ('bot_token_nonce', fields.CharField(max_length=36, null=True, default=None)),
                ('verified', fields.BooleanField(default=False)),
                ('admin', fields.BooleanField(default=False)),
                ('spam_blocked', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now_add=True)),
            ],
            options={'table': 'deletedaccountsnapshot', 'app': 'models', 'pk_attr': 'user_id'},
            bases=['Model'],
        ),
    ]