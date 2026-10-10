"""Data migration to sync initial active families into ItemFamily model."""

from django.db import migrations


def sync_families_forward(apps, schema_editor):
    ItemFamily = apps.get_model("assessment", "ItemFamily")
    from assessment.engine_adapter import all_family_metas

    for meta in all_family_metas():
        ItemFamily.objects.update_or_create(
            id=meta.id,
            defaults={
                "specs": [meta.spec],
                "topic": meta.topic,
                "skills": meta.skills,
                "format": meta.format,
                "a": meta.a,
                "b": meta.b,
                "c": meta.c,
                "time_limit_s": meta.time_limit_s,
                "status": meta.status,
            },
        )


def sync_families_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0006_alter_leaguemembership_options"),
    ]

    operations = [
        migrations.RunPython(sync_families_forward, sync_families_backward),
    ]
