"""Matching app API views."""
from django.db.models import Q
from rest_framework import permissions, status, views
from rest_framework.response import Response

from core.enums import ConsentType, LeagueStatus, UserRole
from core.errors import FSPAPIError
from core.permissions import IsEmployer
from core.services import ContactAccessService
from matching.models import Company, Position, Shortlist
from matching.scoring import calculate_match_score
from matching.serializers import CompanySerializer, PositionSerializer, TalentShortSerializer
from profiles.models import CandidateProfile


def get_employer_company(user):
    """Retrieve the company for an employer user, or create demo company."""
    membership = user.company_memberships.first()
    if membership:
        return membership.company
    # In demo mode, create default company
    company, _ = Company.objects.get_or_create(
        name=f"Компания {user.email.split('@')[0]}",
        defaults={'contact_email': user.email, 'email_domain': user.email.split('@')[-1]}
    )
    from matching.models import CompanyMember
    CompanyMember.objects.get_or_create(company=company, user=user)
    return company


from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

class CompanyMeView(views.APIView):
    permission_classes = [IsEmployer]
    serializer_class = CompanySerializer

    @extend_schema(responses={200: CompanySerializer})
    def get(self, request):
        company = get_employer_company(request.user)
        return Response(CompanySerializer(company).data)

    @extend_schema(request=CompanySerializer, responses={200: CompanySerializer})
    def put(self, request):
        company = get_employer_company(request.user)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if not serializer.is_valid():
            raise FSPAPIError('validation_failed', 'Validation failed', errors=serializer.errors, status_code=422)
        serializer.save()
        return Response(serializer.data)


class PositionListCreateView(views.APIView):
    permission_classes = [IsEmployer]
    serializer_class = PositionSerializer

    @extend_schema(responses={200: PositionSerializer(many=True)})
    def get(self, request):
        company = get_employer_company(request.user)
        positions = Position.objects.filter(company=company).order_by('-created_at')
        return Response(PositionSerializer(positions, many=True).data)

    @extend_schema(request=PositionSerializer, responses={201: PositionSerializer})
    def post(self, request):
        company = get_employer_company(request.user)
        data = request.data.copy()
        data['company'] = str(company.id)
        serializer = PositionSerializer(data=data)
        if not serializer.is_valid():
            raise FSPAPIError('salary_invalid', 'Invalid position data', errors=serializer.errors, status_code=422)
        position = serializer.save()
        return Response(PositionSerializer(position).data, status=status.HTTP_201_CREATED)


class PositionDetailView(views.APIView):
    permission_classes = [IsEmployer]
    serializer_class = PositionSerializer

    @extend_schema(responses={200: PositionSerializer})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)
        return Response(PositionSerializer(position).data)

    @extend_schema(request=PositionSerializer, responses={200: PositionSerializer})
    def put(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)
        serializer = PositionSerializer(position, data=request.data, partial=True)
        if not serializer.is_valid():
            raise FSPAPIError('validation_failed', 'Validation failed', errors=serializer.errors, status_code=422)
        serializer.save()
        return Response(PositionSerializer(position).data)


class PositionPoolView(views.APIView):
    """Scouted talent pool for a position with explainable scores and reason chips."""
    permission_classes = [IsEmployer]

    @extend_schema(responses={200: inline_serializer('PositionPoolResponse', fields={
        'items': serializers.ListField(child=inline_serializer('PoolItem', fields={
            'talent': TalentShortSerializer(),
            'score': serializers.FloatField(),
            'components': serializers.DictField(),
            'reasons': serializers.ListField(child=serializers.DictField()),
            'shortlisted': serializers.BooleanField(),
        })),
        'total': serializers.IntegerField(),
        'page': serializers.IntegerField(),
    })})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)

        # Invariant: only candidates with verified email, publication consent, open_to_offers=True
        candidates_qs = CandidateProfile.objects.filter(
            open_to_offers=True,
            user__email_verified_at__isnull=False,
            user__consents__type=ConsentType.PUBLICATION,
            user__consents__granted=True,
        ).distinct()

        # Filter out blocked companies
        candidates_qs = [c for c in candidates_qs if company.id not in (c.blocked_company_ids or [])]

        shortlisted_user_ids = set(
            Shortlist.objects.filter(position=position).values_list('candidate_id', flat=True)
        )

        pool_items = []
        for candidate in candidates_qs:
            score_data = calculate_match_score(candidate, position)
            pool_items.append({
                'talent': TalentShortSerializer(candidate).data,
                'score': score_data['total_score'],
                'components': score_data['components'],
                'reasons': score_data['reasons'],
                'shortlisted': candidate.user_id in shortlisted_user_ids,
            })

        # Sort by total score descending
        pool_items.sort(key=lambda x: x['score'], reverse=True)

        return Response({
            'items': pool_items,
            'total': len(pool_items),
            'page': 1,
        })


class PositionShortlistView(views.APIView):
    permission_classes = [IsEmployer]

    @extend_schema(responses={204: None})
    def put(self, request, pk, public_id):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        Shortlist.objects.get_or_create(position=position, candidate=profile.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={204: None})
    def delete(self, request, pk, public_id):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        Shortlist.objects.filter(position=position, candidate=profile.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TalentSearchView(views.APIView):
    """General talent search without a specific position."""
    permission_classes = [IsEmployer]
    serializer_class = TalentShortSerializer

    @extend_schema(responses={200: inline_serializer('TalentSearchResponse', fields={
        'items': TalentShortSerializer(many=True),
        'total': serializers.IntegerField(),
        'page': serializers.IntegerField(),
    })})
    def get(self, request):
        candidates = CandidateProfile.objects.filter(
            open_to_offers=True,
            user__email_verified_at__isnull=False,
            user__consents__type=ConsentType.PUBLICATION,
            user__consents__granted=True,
        ).distinct()

        items = [TalentShortSerializer(c).data for c in candidates]
        return Response({'items': items, 'total': len(items), 'page': 1})


class TalentDetailView(views.APIView):
    """Talent card view for employers.

    SECURITY INVARIANT: Contacts are only unmasked if an active ContactGrant exists!
    """
    permission_classes = [IsEmployer]

    @extend_schema(responses={200: inline_serializer('TalentDetailResponse', fields={
        'public_id': serializers.CharField(),
        'city': serializers.CharField(),
        'work_formats': serializers.ListField(child=serializers.CharField()),
        'salary_min': serializers.IntegerField(allow_null=True),
        'salary_max': serializers.IntegerField(allow_null=True),
        'salary_type': serializers.CharField(),
        'league': serializers.DictField(allow_null=True),
        'fsp': serializers.DictField(),
        'skills': serializers.ListField(child=serializers.DictField()),
        'about': serializers.CharField(),
        'experience_text': serializers.CharField(),
        'contacts': serializers.DictField(allow_null=True),
    })})
    def get(self, request, public_id):
        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        company = get_employer_company(request.user)

        data = TalentShortSerializer(profile).data
        data['about'] = profile.about
        data['experience_text'] = profile.experience_text

        # Check contact grant
        if ContactAccessService.has_active_grant(company.id, profile.user_id):
            contacts = ContactAccessService.get_contacts(company.id, profile.user_id, actor_id=request.user.id)
            data['contacts'] = {
                'full_name': contacts.full_name,
                'email': contacts.email,
                'phone': contacts.phone,
                'telegram': contacts.telegram,
            }
        else:
            data['contacts'] = None

        return Response(data)
