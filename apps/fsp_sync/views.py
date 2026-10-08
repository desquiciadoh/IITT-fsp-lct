"""FSP Sync views and mock registry integration."""
import hashlib
from datetime import date
from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.response import Response

from core.enums import Discipline, PlacementTier, SportsRank, SyncStatus
from core.errors import FSPAPIError, FSPIdAlreadyLinked
from core.permissions import IsCandidate
from fsp_sync.models import FSPLink, FSPResult
from assessment.models import LeagueMembership


MOCK_REGISTRY = {
    'FSP-000123': {
        'sports_rank': SportsRank.KMS,
        'results': [
            {
                'event_id': 'CHAMP-2025',
                'event_name': 'Чемпионат России по спортивному программированию 2025',
                'discipline': Discipline.ALGORITHMIC,
                'date': '2025-11-20',
                'stage': 'Финал',
                'format': 'individual',
                'placement': 2,
                'tier': PlacementTier.PRIZE_WINNER,
                'participants_total': 180,
            },
            {
                'event_id': 'CUP-2025',
                'event_name': 'Кубок Федерации 2025 (Продуктовое программирование)',
                'discipline': Discipline.PRODUCT,
                'date': '2025-06-15',
                'stage': 'Финал',
                'format': 'team',
                'team_size': 4,
                'placement': 1,
                'tier': PlacementTier.WINNER,
                'participants_total': 64,
            }
        ]
    },
    'FSP-000456': {
        'sports_rank': SportsRank.CAT1,
        'results': [
            {
                'event_id': 'MOSCOW-2025',
                'event_name': 'Первенство Москвы 2025',
                'discipline': Discipline.INFOSEC,
                'date': '2025-09-10',
                'stage': 'Финал',
                'format': 'individual',
                'placement': 3,
                'tier': PlacementTier.PRIZE_WINNER,
                'participants_total': 120,
            }
        ]
    }
}


def sync_candidate_fsp_data(candidate, participant_id: str):
    """Sync FSP achievements from mock registry into DB.

    CRITICAL INVARIANT: FSP achievements recalculate Profile Strength,
    but NEVER alter the candidate's Grade!
    """
    link, _ = FSPLink.objects.get_or_create(
        candidate=candidate,
        defaults={'participant_id': participant_id}
    )

    data = MOCK_REGISTRY.get(participant_id, {})
    if data:
        link.sports_rank = data.get('sports_rank', '')
    link.sync_status = SyncStatus.OK
    link.last_sync_at = timezone.now()
    link.save()

    for item in data.get('results', []):
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

    # Recalculate profile strength in LeagueMembership WITHOUT touching grade!
    for lm in candidate.league_memberships.all():
        old_grade = lm.grade  # Invariant: grade must not change!
        results_count = candidate.fsp_results.count()
        fsp_boost = min(15.0, results_count * 5.0)
        lm.strength = min(100.0, lm.strength + fsp_boost)
        lm.save(update_fields=['strength'])
        assert lm.grade == old_grade, "INVARIANT VIOLATION: Grade changed by FSP achievements!"

    return link


from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

class FSPLinkView(views.APIView):
    permission_classes = [IsCandidate]

    @extend_schema(
        request=inline_serializer('FSPLinkRequest', fields={'participant_id': serializers.CharField()}),
        responses={200: inline_serializer('FSPLinkResponse', fields={
            'participant_id': serializers.CharField(),
            'sports_rank': serializers.CharField(),
            'sync_status': serializers.CharField(),
            'results_count': serializers.IntegerField(),
        })}
    )
    def post(self, request):
        participant_id = request.data.get('participant_id')
        if not participant_id:
            raise FSPAPIError('validation_failed', 'Missing ID', 'participant_id is required', 422)

        # Invariant: Check if already linked to another candidate
        existing = FSPLink.objects.filter(participant_id=participant_id).exclude(candidate=request.user).first()
        if existing:
            raise FSPIdAlreadyLinked()

        link = sync_candidate_fsp_data(request.user, participant_id)

        return Response({
            'participant_id': link.participant_id,
            'sports_rank': link.sports_rank,
            'sync_status': link.sync_status,
            'results_count': request.user.fsp_results.count(),
        })


class FSPSyncTaskTriggerView(views.APIView):
    """Trigger background or immediate sync of FSP achievements."""
    permission_classes = [IsCandidate]

    @extend_schema(responses={200: inline_serializer('FSPSyncResponse', fields={'status': serializers.CharField(), 'synced_at': serializers.CharField()})})
    def post(self, request):
        link = FSPLink.objects.filter(candidate=request.user).first()
        if not link:
            raise FSPAPIError('not_found', 'Not linked', 'FSP ID is not linked', 404)

        sync_candidate_fsp_data(request.user, link.participant_id)
        return Response({'status': 'ok', 'synced_at': timezone.now().isoformat()})
