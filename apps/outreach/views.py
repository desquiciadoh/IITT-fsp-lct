"""Outreach app views: Offer lifecycle with optimistic locking and SSE streaming."""
import json
import time
from django.http import StreamingHttpResponse
from rest_framework import permissions, status, views
from rest_framework.response import Response

from core.enums import OfferStatus, UserRole
from core.errors import FSPAPIError, SalaryInvalid
from core.permissions import IsEmployer
from matching.views import get_employer_company
from outreach.models import Offer
from outreach.serializers import OfferSerializer
from outreach.services import OfferService
from profiles.models import CandidateProfile


from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

class OfferListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsEmployer()]
        return super().get_permissions()

    @extend_schema(responses={200: OfferSerializer(many=True)})
    def get(self, request):
        user = request.user
        if user.role == UserRole.CANDIDATE:
            offers = Offer.objects.filter(candidate=user).order_by('-created_at')
        else:
            company = get_employer_company(user)
            offers = Offer.objects.filter(company=company).order_by('-created_at')

        status_param = request.query_params.get('status')
        if status_param:
            offers = offers.filter(status=status_param)

        serializer = OfferSerializer(offers, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(request=OfferSerializer, responses={201: OfferSerializer})
    def post(self, request):
        company = get_employer_company(request.user)
        public_id = request.data.get('candidate_public_id')
        if not public_id:
            raise FSPAPIError('validation_failed', 'Missing candidate', 'candidate_public_id is required', 422)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        salary_min = request.data.get('salary_min')
        salary_max = request.data.get('salary_max')
        salary_type = request.data.get('salary_type', 'gross')

        if not salary_min or int(salary_min) <= 0:
            raise SalaryInvalid('salary_min must be positive integer')
        if not salary_max or int(salary_max) < int(salary_min):
            raise SalaryInvalid('salary_max must be >= salary_min')

        offer = OfferService.create_offer(
            company_id=company.id,
            candidate_id=profile.user_id,
            created_by_id=request.user.id,
            title=request.data.get('title', 'Draft Offer'),
            description=request.data.get('description', ''),
            salary_min=int(salary_min),
            salary_max=int(salary_max),
            salary_type=salary_type,
            contact_channel=request.data.get('contact_channel', 'email'),
            contact_value=request.data.get('contact_value', request.user.email),
            position_id=request.data.get('position_id'),
            why_you=request.data.get('why_you', []),
        )

        return Response(
            OfferSerializer(offer, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class OfferDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    @extend_schema(responses={200: OfferSerializer})
    def get(self, request, pk):
        if request.user.role == UserRole.CANDIDATE:
            offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        elif request.user.role == UserRole.EMPLOYER:
            offer = Offer.objects.filter(
                id=pk,
                company=get_employer_company(request.user),
            ).first()
        else:
            offer = None
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)
        return Response(OfferSerializer(offer, context={'request': request}).data)


class OfferViewActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    @extend_schema(
        request=inline_serializer('OfferViewRequest', fields={'version': serializers.IntegerField()}),
        responses={200: OfferSerializer}
    )
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        version = int(request.data.get('version', offer.version))
        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=version,
            actor_id=request.user.id
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferAcceptActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    @extend_schema(
        request=inline_serializer('OfferAcceptRequest', fields={'version': serializers.IntegerField()}),
        responses={200: OfferSerializer}
    )
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        version = int(request.data.get('version', offer.version))
        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.ACCEPTED,
            expected_version=version,
            actor_id=request.user.id
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferDeclineActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    @extend_schema(
        request=inline_serializer('OfferDeclineRequest', fields={
            'version': serializers.IntegerField(),
            'reason': serializers.CharField(default='salary'),
            'comment': serializers.CharField(required=False, allow_blank=True),
        }),
        responses={200: OfferSerializer}
    )
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        version = int(request.data.get('version', offer.version))
        reason = request.data.get('reason', 'other')
        comment = request.data.get('comment', '')

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.DECLINED,
            expected_version=version,
            actor_id=request.user.id,
            decline_reason=reason,
            decline_comment=comment
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferWithdrawActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    @extend_schema(
        request=inline_serializer('OfferWithdrawRequest', fields={'version': serializers.IntegerField()}),
        responses={200: OfferSerializer}
    )
    def post(self, request, pk):
        company = get_employer_company(request.user)
        offer = Offer.objects.filter(id=pk, company=company).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        version = int(request.data.get('version', offer.version))
        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.WITHDRAWN,
            expected_version=version,
            actor_id=request.user.id
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class SSEEventsView(views.APIView):
    """Server-Sent Events (SSE) endpoint for real-time notifications."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        def event_stream():
            yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"
            # Keepalive ping
            for _ in range(3):
                time.sleep(1)
                yield f": ping {time.time()}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
