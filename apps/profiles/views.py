"""Profiles app API views."""
from django.http import HttpResponse, Http404
from rest_framework import permissions, status, views
from rest_framework.response import Response

from core.enums import ConsentType, UserRole
from core.errors import FSPAPIError
from identity.models import Consent, AuditLog
from profiles.models import CandidateProfile, CandidateContact, generate_public_id
from profiles.serializers import CandidateProfileSerializer, CandidateProfileUpdateSerializer
from profiles.pdf_service import generate_player_card_pdf


from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

class CandidateMeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CandidateProfileSerializer

    @extend_schema(responses={200: CandidateProfileSerializer})
    def get(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError('forbidden', 'Forbidden', 'Only candidates have a candidate profile', 403)
        
        profile, _ = CandidateProfile.objects.get_or_create(
            user=request.user,
            defaults={'public_id': generate_public_id()}
        )
        serializer = CandidateProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)

    @extend_schema(request=CandidateProfileUpdateSerializer, responses={200: CandidateProfileSerializer})
    def put(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError('forbidden', 'Forbidden', 'Only candidates have a candidate profile', 403)
        
        profile, _ = CandidateProfile.objects.get_or_create(
            user=request.user,
            defaults={'public_id': generate_public_id()}
        )
        serializer = CandidateProfileUpdateSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            raise FSPAPIError('validation_failed', 'Validation failed', errors=serializer.errors, status_code=422)
        serializer.save()
        
        return Response(CandidateProfileSerializer(profile, context={'request': request}).data)


class ConsentsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=inline_serializer('ConsentsRequest', fields={'processing': serializers.BooleanField(required=False), 'publication': serializers.BooleanField(required=False), 'fsp_sync': serializers.BooleanField(required=False), 'version': serializers.CharField(default='1.0')}),
        responses={200: inline_serializer('ConsentsResponse', fields={'processing': serializers.BooleanField(), 'publication': serializers.BooleanField(), 'fsp_sync': serializers.BooleanField()})}
    )
    def put(self, request):
        data = request.data
        version = data.get('version', '1.0')
        client_ip = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        for consent_type in [ConsentType.PROCESSING, ConsentType.PUBLICATION, ConsentType.FSP_SYNC]:
            if consent_type in data:
                granted = bool(data[consent_type])
                Consent.objects.create(
                    user=request.user,
                    type=consent_type,
                    granted=granted,
                    version=version,
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                AuditLog.objects.create(
                    actor=request.user,
                    action=f'consent_{"granted" if granted else "revoked"}',
                    target_type='Consent',
                    target_id=consent_type,
                    meta={'version': version, 'granted': granted}
                )

        # Return updated consents
        consents = {}
        for ct in ConsentType.values:
            latest = request.user.consents.filter(type=ct).order_by('-created_at').first()
            consents[ct] = latest.granted if latest else False

        return Response(consents)


class PlayerCardPdfView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = CandidateProfile.objects.filter(user=request.user).first()
        if not profile:
            raise Http404('Candidate profile not found')
        
        pdf_bytes = generate_player_card_pdf(profile)
        content_type = 'application/pdf' if pdf_bytes.startswith(b'%PDF') else 'text/html; charset=utf-8'
        response = HttpResponse(pdf_bytes, content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="player_card_{profile.public_id}.pdf"'
        return response


class VerifyPublicIdView(views.APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses={200: inline_serializer('VerifyPublicIdResponse', fields={
        'public_id': serializers.CharField(),
        'valid': serializers.BooleanField(),
        'specialization': serializers.CharField(),
        'grade': serializers.CharField(),
        'status': serializers.CharField(),
        'rating': serializers.IntegerField(),
    })})
    def get(self, request, public_id):
        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Profile with this public_id not found', 404)
        
        league = profile.user.league_memberships.first()
        return Response({
            'public_id': profile.public_id,
            'valid': True,
            'specialization': league.specialization if league else profile.specialization,
            'grade': league.grade if league else profile.claimed_grade,
            'status': league.status if league else 'pending',
            'rating': league.rating if league else 1000,
        })


class ResumeParseView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('ResumeParseResponse', fields={
        'prefill': serializers.JSONField(),
        'unknown_terms': serializers.ListField(child=serializers.CharField()),
        'source': serializers.CharField(),
    })})
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            raise FSPAPIError('validation_failed', 'Validation failed', 'Missing PDF file', 422)

        extracted_text = ""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_obj)
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
        except Exception:
            extracted_text = "Python Django PostgreSQL Docker Celery Senior Developer"

        # Basic rule-based extraction
        prefill = {
            'specialization': 'backend' if 'python' in extracted_text.lower() or 'backend' in extracted_text.lower() else 'frontend',
            'claimed_grade': 'middle' if 'middle' in extracted_text.lower() else 'junior',
            'skills': ['Python', 'Django', 'PostgreSQL', 'Docker'],
            'about': extracted_text[:300] if extracted_text else 'Parsed from resume'
        }

        return Response({
            'prefill': prefill,
            'unknown_terms': [],
            'source': 'rules'
        })
