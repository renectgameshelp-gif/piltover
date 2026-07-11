from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0062_group_calls')]

    initial = False

    operations = [
        ops.AddField(
            model_name='GroupCallParticipant',
            name='raise_hand_rating',
            field=fields.BigIntField(null=True, default=None),
        ),
        ops.AddField(
            model_name='GroupCallParticipant',
            name='muted_by_admin',
            field=fields.BooleanField(default=False),
        ),
    ]