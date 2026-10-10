"""Celery tasks for assessment application."""

import logging

from celery import shared_task

from assessment.services import AssessmentService

logger = logging.getLogger(__name__)


@shared_task(name="assessment.tasks.sweep_stale_assessments")
def sweep_stale_assessments():
    """Sweep stale in-progress assessment sessions."""
    count = AssessmentService.sweep_stale_sessions()
    logger.info("Swept %d stale assessment sessions.", count)
    return count
