"""FSP Sync views — thin wrappers delegating to fsp_sync.services."""
from core.errors import FSPAPIError, FSPIdAlreadyLinked
from core.permissions import IsCandidate
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, views
from rest_framework.response import Response

from fsp_sync.models import FSPLink
from fsp_sync.services import link_fsp_id, sync_fsp_data


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
        # Outside DEMO_MODE ownership must be proven via OIDC
        # (GET /api/auth/fsp-id/login?intent=link); a bare ID is just a claim.
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                'fsp_oidc_required',
                'FSP ID verification required',
                'Link FSP ID via /api/auth/fsp-id/login?intent=link',
                403,
            )
        participant_id = request.data.get('participant_id')
        if not participant_id:
            raise FSPAPIError('validation_failed', 'Missing ID', 'participant_id is required', 422)

        # Invariant: Check if already linked to another candidate
        existing = FSPLink.objects.filter(participant_id=participant_id).exclude(candidate=request.user).first()
        if existing:
            raise FSPIdAlreadyLinked()

        link = link_fsp_id(request.user, participant_id)

        return Response({
            'participant_id': link.participant_id,
            'sports_rank': link.sports_rank,
            'sync_status': link.sync_status,
            'results_count': request.user.fsp_results.count(),
        })


class FSPSyncTaskTriggerView(views.APIView):
    """Trigger background or immediate sync of FSP achievements."""
    permission_classes = [IsCandidate]

    @extend_schema(
        request=None,
        responses={200: inline_serializer('FSPSyncResponse', fields={'status': serializers.CharField(), 'synced_at': serializers.CharField()})}
    )
    def post(self, request):
        link = FSPLink.objects.filter(candidate=request.user).first()
        if not link:
            raise FSPAPIError('not_found', 'Not linked', 'FSP ID is not linked', 404)

        sync_fsp_data(request.user, link)
        return Response({'status': 'ok', 'synced_at': timezone.now().isoformat()})
