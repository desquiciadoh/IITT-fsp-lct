"""Celery tasks for FSP sync."""
from celery import shared_task
from identity.models import User
from fsp_sync.models import FSPLink
from fsp_sync.views import sync_candidate_fsp_data


@shared_task
def sync_all_fsp_profiles():
    """Periodic Celery task to re-sync all linked FSP profiles."""
    links = FSPLink.objects.select_related('candidate').all()
    synced_count = 0
    for link in links:
        try:
            sync_candidate_fsp_data(link.candidate, link.participant_id)
            synced_count += 1
        except Exception:
            pass
    return f"Synced {synced_count} FSP profiles"
