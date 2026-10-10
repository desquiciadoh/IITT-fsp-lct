from django.db import migrations, models


def expire_duplicate_in_progress(apps, schema_editor):
    """Keep only the newest in-progress session per candidate+specialization.

    Older duplicates (created by the pre-constraint race) are marked expired so
    the partial unique index can be built.
    """
    Session = apps.get_model('assessment', 'AssessmentSession')
    seen = set()
    rows = (
        Session.objects.filter(status='in_progress')
        .order_by('candidate_id', 'specialization', '-started_at', '-id')
        .values_list('id', 'candidate_id', 'specialization', 'started_at')
    )
    stale_ids = []
    for pk, candidate_id, spec, _started in rows:
        key = (candidate_id, spec)
        if key in seen:
            stale_ids.append(pk)
        else:
            seen.add(key)
    if stale_ids:
        from django.utils import timezone

        Session.objects.filter(id__in=stale_ids).update(status='expired', finished_at=timezone.now())


def backfill_null_deadlines(apps, schema_editor):
    """Backfill NULL deadline_at with served_at (or now) before reverting to NOT NULL on rollback."""
    AssessmentItem = apps.get_model('assessment', 'AssessmentItem')
    from django.utils import timezone

    AssessmentItem.objects.filter(deadline_at__isnull=True).update(deadline_at=models.F('served_at'))
    AssessmentItem.objects.filter(deadline_at__isnull=True).update(deadline_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0003_leaguemembership_base_strength_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assessmentitem',
            name='deadline_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Item-level deadline; set when the item becomes current, NULL until served',
                null=True,
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, reverse_code=backfill_null_deadlines),
        migrations.RunPython(expire_duplicate_in_progress, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='assessmentsession',
            constraint=models.UniqueConstraint(
                condition=models.Q(status='in_progress'),
                fields=('candidate', 'specialization'),
                name='uq_one_in_progress_assessment_per_spec',
            ),
        ),
    ]
