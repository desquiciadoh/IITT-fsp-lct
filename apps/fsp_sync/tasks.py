"""Celery tasks for FSP sync."""
import logging

from celery import shared_task

from fsp_sync.models import FSPLink
from fsp_sync.services import sync_candidate_fsp_data

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_all_fsp_profiles(self):
    """Periodic Celery task to re-sync all linked FSP profiles."""
    links = FSPLink.objects.select_related('candidate').all()
    synced_count = 0
    for link in links:
        try:
            sync_candidate_fsp_data(link.candidate, link.participant_id)
            synced_count += 1
        except Exception as exc:
            logger.warning("Failed to sync FSP profile for %s: %s", link.participant_id, exc)
    return f"Synced {synced_count} FSP profiles"
