"""Celery tasks for FSP sync."""

import logging

from celery import shared_task

from fsp_sync.models import FSPLink
from fsp_sync.services import sync_candidate_fsp_data

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_all_fsp_profiles(self):
    """Periodic Celery task to re-sync all linked FSP profiles."""
    links = FSPLink.objects.select_related("candidate").all()
    ok = []
    failed = []
    for link in links:
        try:
            sync_candidate_fsp_data(link.candidate, link.participant_id)
            ok.append(link.participant_id)
        except Exception:
            logger.exception(
                "Failed to sync FSP profile for %s (candidate ID %s)",
                link.participant_id,
                link.candidate_id,
            )
            failed.append(link.participant_id)
    return {"ok": ok, "failed": failed}
