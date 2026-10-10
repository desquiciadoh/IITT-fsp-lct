from __future__ import annotations

import dataclasses
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="llm_gateway.parse_jd", queue="llm")
def parse_jd_task(text: str) -> dict:
    """Celery task to parse a vacancy job description in the llm worker pool."""
    import importlib

    try:
        gateway = importlib.import_module("llm_gateway")
        parse_jd = gateway.parse_jd
    except (ImportError, AttributeError):
        logger.warning("llm_gateway package is not available")
        raise

    result = parse_jd(text)
    return dataclasses.asdict(result)


@shared_task(name="matching.drop_weekly_microtasks")
def drop_weekly_microtasks_task() -> int:
    """Weekly drop cron (Task BE-18).

    Distributes periodic micro-tasks to matching candidates to keep profiles active.
    """
    from django.db import models
    from django.utils import timezone
    from outreach.events import publish_domain_event
    from profiles.models import CandidateProfile

    from matching.models import MicroTask, MicroTaskDrop

    now = timezone.now()
    active_tasks = MicroTask.objects.filter(
        models.Q(deadline__isnull=True) | models.Q(deadline__gt=now)
    )

    created_count = 0
    for task in active_tasks:
        candidates_qs = CandidateProfile.objects.filter(
            specialization=task.specialization,
            open_to_offers=True,
        ).select_related("user")

        for profile in candidates_qs:
            # Check grade matching (using claimed_grade on profile)
            cand_grade = getattr(profile, "claimed_grade", "") or getattr(profile, "grade", "")
            if task.grades and cand_grade not in task.grades:
                continue

            drop, created = MicroTaskDrop.objects.get_or_create(
                task=task,
                candidate=profile.user,
            )
            if created:
                created_count += 1
                try:
                    publish_domain_event(
                        "microtask_dropped",
                        {
                            "drop_id": str(drop.id),
                            "task_id": str(task.id),
                            "candidate_id": str(profile.user_id),
                            "title": task.title,
                        },
                    )
                except Exception as e:
                    logger.debug("Failed to publish microtask drop event: %s", e)

    logger.info("Weekly micro-task drop completed: %d new drops created", created_count)
    return created_count

