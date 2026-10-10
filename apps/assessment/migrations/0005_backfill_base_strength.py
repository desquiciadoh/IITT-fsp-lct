from django.db import migrations
from django.db.models import F


def backfill_base_strength(apps, schema_editor):
    LeagueMembership = apps.get_model('assessment', 'LeagueMembership')
    LeagueMembership.objects.filter(
        base_strength=0.0,
        strength__gt=0.0,
    ).update(base_strength=F('strength'))


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0004_item_deadline_on_serve_one_active_session'),
    ]

    operations = [
        migrations.RunPython(backfill_base_strength, reverse_code=migrations.RunPython.noop),
    ]
