"""Outreach app views: Offer lifecycle with optimistic locking and SSE streaming."""
import json
import time

from core.enums import DeclineReason, OfferStatus, UserRole
from core.errors import CandidateNotReachable, FSPAPIError
from core.pagination import FSPPagination
from core.permissions import IsCandidate, IsEmployer
from django.http import StreamingHttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from matching.views import get_employer_company
from profiles.models import CandidateProfile
from profiles.selectors import is_candidate_visible_to_company
from rest_framework import permissions, serializers, status, views
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response

from outreach.models import Offer
from outreach.serializers import (
    CreateOfferSerializer,
    OfferActionSerializer,
    OfferSerializer,
)
from outreach.services import OfferService


class EventStreamRenderer(BaseRenderer):
    """Renderer for text/event-stream (SSE)."""
    media_type = 'text/event-stream'
    format = 'event-stream'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class OfferListCreateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OfferSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsEmployer()]
        return super().get_permissions()

    @extend_schema(responses={200: inline_serializer('OfferPaginatedResponse', fields={
        'items': OfferSerializer(many=True),
        'total': serializers.IntegerField(),
        'page': serializers.IntegerField(),
        'pages': serializers.IntegerField(),
    })})
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

        paginator = FSPPagination()
        page = paginator.paginate_queryset(offers, request, view=self)
        if page is not None:
            serializer = OfferSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = OfferSerializer(offers, many=True, context={'request': request})
        return Response({
            'items': serializer.data,
            'total': len(serializer.data),
            'page': 1,
            'pages': 1,
        })

    @extend_schema(request=CreateOfferSerializer, responses={201: OfferSerializer})
    def post(self, request):
        company = get_employer_company(request.user)

        serializer = CreateOfferSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        data = serializer.validated_data

        public_id = data['candidate_public_id']
        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        if not is_candidate_visible_to_company(profile, company):
            raise CandidateNotReachable()

        position_id = data.get('position')
        if position_id:
            from matching.models import Position
            if not Position.objects.filter(id=position_id, company=company).exists():
                raise FSPAPIError(
                    'validation_failed',
                    'Invalid position',
                    'Position must belong to your company',
                    422,
                )

        offer = OfferService.create_offer(
            company_id=company.id,
            candidate_id=profile.user_id,
            created_by_id=request.user.id,
            title=data.get('title', 'Draft Offer'),
            description=data.get('description', ''),
            salary_min=data['salary_min'],
            salary_max=data['salary_max'],
            salary_type=data['salary_type'],
            contact_channel=data['contact_channel'],
            contact_value=data['contact_value'],
            position_id=position_id,
        )

        return Response(
            OfferSerializer(offer, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
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
    permission_classes = [permissions.IsAuthenticated, IsCandidate]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferAcceptActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsCandidate]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.ACCEPTED,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferDeclineActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsCandidate]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        offer = Offer.objects.filter(id=pk, candidate=request.user).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )

        version = serializer.validated_data['version']
        reason = serializer.validated_data.get('reason') or DeclineReason.OTHER
        comment = serializer.validated_data.get('comment', '')

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.DECLINED,
            expected_version=version,
            actor_id=request.user.id,
            decline_reason=reason,
            decline_comment=comment,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferWithdrawActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        company = get_employer_company(request.user)
        offer = Offer.objects.filter(id=pk, company=company).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.WITHDRAWN,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferInterviewActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        company = get_employer_company(request.user)
        offer = Offer.objects.filter(id=pk, company=company).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.INTERVIEW,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferHiredActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        company = get_employer_company(request.user)
        offer = Offer.objects.filter(id=pk, company=company).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.HIRED,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class OfferCloseActionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployer]
    serializer_class = OfferActionSerializer

    @extend_schema(request=OfferActionSerializer, responses={200: OfferSerializer})
    def post(self, request, pk):
        company = get_employer_company(request.user)
        offer = Offer.objects.filter(id=pk, company=company).first()
        if not offer:
            raise FSPAPIError('not_found', 'Not found', 'Offer not found', 404)

        serializer = OfferActionSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        version = serializer.validated_data['version']

        updated_offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.CLOSED,
            expected_version=version,
            actor_id=request.user.id,
        )
        return Response(OfferSerializer(updated_offer, context={'request': request}).data)


class SSEEventsView(views.APIView):
    """Server-Sent Events (SSE) endpoint for real-time notifications."""
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [EventStreamRenderer]
    MAX_LIMIT = 1000

    @extend_schema(
        responses={(200, 'text/event-stream'): str},
        description='Server-Sent Events (SSE) notification stream',
    )
    def get(self, request):
        import queue

        from django.http import HttpResponse

        from outreach.events import register_subscriber, unregister_subscriber

        # Validate before the 200 headers go out; a streaming body cannot carry an error.
        raw_limit = request.query_params.get('limit', '0')
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = -1
        if limit < 0 or limit > self.MAX_LIMIT:
            problem = {
                'type': 'https://fsp-draft.local/problems/validation_failed',
                'title': 'Validation failed',
                'status': 422,
                'code': 'validation_failed',
                'detail': 'One or more fields failed validation.',
                'errors': [{'field': 'limit', 'msg': f'Must be an integer between 0 and {self.MAX_LIMIT}.'}],
            }
            return HttpResponse(json.dumps(problem), status=422, content_type='application/problem+json')

        user_id = request.user.id
        company_ids = list(request.user.company_memberships.values_list('company_id', flat=True))

        def event_stream():
            sub = register_subscriber(user_id=user_id, company_ids=company_ids, replay_recent=True)
            try:
                yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"

                count = 0
                # Run until disconnected; with a limit (e.g. tests), stop after `limit` events.
                while True:
                    try:
                        msg = sub.get(timeout=1.0 if limit else 15.0)
                        event_name = msg.get('event', 'message')
                        data_json = json.dumps(msg.get('data', {}), default=str)
                        yield f"event: {event_name}\ndata: {data_json}\n\n"
                        count += 1
                        if limit and count >= limit:
                            break
                    except queue.Empty:
                        yield f": keepalive {time.time()}\n\n"
                        if limit:
                            break
            finally:
                unregister_subscriber(sub)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

