"""FSP Sync service layer — OIDC-aware linking and idempotent strength recompute.

This module owns all FSP data synchronization logic.
Views delegate to these functions; they should not contain business logic.
"""
import hashlib
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from assessment.models import LeagueMembership
from core.enums import SyncStatus
from core.errors import FSPIdAlreadyLinked
from fsp_sync.models import FSPLink, FSPResult
from fsp_sync.registry import get_registry_data
from outreach.events import publish_domain_event

logger = logging.getLogger(__name__)


@transaction.atomic
def link_fsp_id(candidate, participant_id: str) -> FSPLink:
    """Create or update the FSP link for a candidate, then sync data.

    Enforces invariants:
    1. A participant_id cannot be linked to multiple candidates (raises FSPIdAlreadyLinked).
    2. Relinking cleanly replaces previous competition results.
    3. Operation is wrapped in transaction.atomic and catches IntegrityError.
    """
    existing = FSPLink.objects.filter(participant_id=participant_id).exclude(candidate=candidate).first()
    if existing:
        raise FSPIdAlreadyLinked()

    try:
        link = FSPLink.objects.select_for_update().filter(candidate=candidate).first()
        if link:
            if link.participant_id != participant_id:
                candidate.fsp_results.all().delete()
                link.participant_id = participant_id
                link.save(update_fields=['participant_id'])
        else:
            link = FSPLink.objects.create(
                candidate=candidate,
                participant_id=participant_id,
            )
    except IntegrityError:
        raise FSPIdAlreadyLinked()

    return sync_fsp_data(candidate, link)


# Backward compatibility alias
sync_candidate_fsp_data = link_fsp_id


def sync_fsp_data(candidate, link: FSPLink) -> FSPLink:
    """Pull latest data from registry and recompute strength idempotently."""
    data = get_registry_data(link.participant_id)

    if data:
        link.sports_rank = data.get('sports_rank', '')
    link.sync_status = SyncStatus.OK
    link.last_sync_at = timezone.now()
    link.save()

    _upsert_results(candidate, link.participant_id, data.get('results', []))
    recompute_strength(candidate)

    publish_domain_event('fsp.synced', {
        'candidate_id': str(candidate.id),
        'participant_id': link.participant_id,
        'sports_rank': link.sports_rank,
        'results_count': candidate.fsp_results.count(),
    })

    return link


def _upsert_results(candidate, participant_id: str, results: list):
    """Idempotent upsert of FSP competition results."""
    for item in results:
        source_raw = f"{participant_id}:{item['event_id']}:{item['placement']}"
        source_hash = hashlib.sha256(source_raw.encode()).hexdigest()

        FSPResult.objects.update_or_create(
            candidate=candidate,
            event_id=item['event_id'],
            defaults={
                'event_name': item['event_name'],
                'discipline': item['discipline'],
                'date': item['date'],
                'stage': item.get('stage', ''),
                'format': item.get('format', 'individual'),
                'team_size': item.get('team_size'),
                'placement': item['placement'],
                'tier': item['tier'],
                'participants_total': item['participants_total'],
                'source_hash': source_hash,
            }
        )


def recompute_strength(candidate):
    """Idempotently recompute strength from base + FSP boost.

    CRITICAL INVARIANT: Grade is NEVER altered by FSP achievements.
    """
    results_count = candidate.fsp_results.count()
    fsp_boost = min(15.0, results_count * 5.0)

    updated_memberships = []
    for lm in candidate.league_memberships.all():
        old_grade = lm.grade
        if lm.base_strength == 0.0 and lm.strength > 0.0:
            lm.base_strength = lm.strength
        lm.fsp_boost = fsp_boost
        lm.strength = min(100.0, max(0.0, lm.base_strength + fsp_boost))
        lm.save(update_fields=['base_strength', 'fsp_boost', 'strength'])
        if lm.grade != old_grade:
            raise RuntimeError("INVARIANT VIOLATION: Grade changed by FSP achievements!")
        updated_memberships.append(lm)
    return updated_memberships[0] if updated_memberships else None


# Backward compatibility
_recompute_strength = recompute_strength
