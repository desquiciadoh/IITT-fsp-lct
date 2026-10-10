"""Matching app API views."""
from core.errors import FSPAPIError
from core.permissions import IsEmployer
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from outreach.services import ContactAccessService
from profiles.models import CandidateProfile
from profiles.selectors import is_candidate_visible_to_company, visible_candidates_for
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from matching.models import Company, CompanyMember, Position, Shortlist
from matching.scoring import calculate_match_score
from matching.selectors import compute_pool_facets, filter_candidate_profiles
from matching.serializers import (
    CompanyMinimalSerializer,
    CompanySerializer,
    JdParseRequestSerializer,
    JdParseResultSerializer,
    PositionSerializer,
    TalentShortSerializer,
)


def get_employer_company(user):
    """Retrieve the company for an employer user. Raises 403 if no membership."""
    membership = user.company_memberships.first()
    if membership:
        return membership.company
    raise FSPAPIError(
        'company_required',
        'Company required',
        'Create or join a company before performing employer actions.',
        403
    )


class CompanyListCreateView(views.APIView):
    serializer_class = CompanySerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsEmployer()]
        return [permissions.IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='search',
                description='Search companies by name for candidate blocklist',
                required=False,
                type=str,
            ),
        ],
        responses={200: CompanyMinimalSerializer(many=True)},
    )
    def get(self, request):
        search = request.query_params.get('search', '').strip()
        qs = Company.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)
        companies = qs.order_by('name')[:50]
        return Response(CompanyMinimalSerializer(companies, many=True).data)

    @extend_schema(
        request=CompanySerializer,
        responses={201: CompanySerializer},
    )
    def post(self, request):
        if request.user.company_memberships.exists():
            raise FSPAPIError(
                'company_already_exists',
                'Company already exists',
                'You are already associated with a company.',
                status_code=400,
            )
        serializer = CompanySerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )
        with transaction.atomic():
            company = serializer.save()
            CompanyMember.objects.create(company=company, user=request.user)
        return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


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
        serializer = PositionSerializer(data=request.data)
        if not serializer.is_valid():
            is_salary_err = any(k in serializer.errors for k in ('salary_min', 'salary_max', 'salary_type'))
            err_code = 'salary_invalid' if is_salary_err else 'validation_failed'
            raise FSPAPIError(err_code, 'Validation failed', errors=serializer.errors, status_code=422)
        position = serializer.save(company=company)
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

    @extend_schema(
        parameters=[
            OpenApiParameter('grades', str, description='Comma-separated grades, e.g. junior,middle'),
            OpenApiParameter('skills', str, description='Comma-separated skill IDs or names'),
            OpenApiParameter('fsp', str, description='true/false filter for FSP achievements'),
            OpenApiParameter('formats', str, description='Comma-separated work formats: remote,hybrid,office'),
            OpenApiParameter('salary_max', int, description='Max salary expectations'),
            OpenApiParameter('confirmed_only', str, description='true to show only verified league grades'),
            OpenApiParameter('preset', str, description='Preset filter: fsp_stars, confirmed'),
            OpenApiParameter('page', int, description='Page number (default 1)'),
            OpenApiParameter('size', int, description='Page size (default 20)'),
        ],
        responses={200: inline_serializer('PositionPoolResponse', fields={
            'items': serializers.ListField(child=inline_serializer('PoolItem', fields={
                'talent': TalentShortSerializer(),
                'score': serializers.FloatField(),
                'components': serializers.ListField(child=inline_serializer('PoolComponent', fields={
                    'key': serializers.CharField(),
                    'value': serializers.FloatField(),
                    'weight': serializers.FloatField(),
                    'contribution': serializers.FloatField(),
                })),
                'reasons': serializers.ListField(child=serializers.DictField()),
                'gaps': serializers.ListField(child=serializers.CharField()),
                'shortlisted': serializers.BooleanField(),
            })),
            'total': serializers.IntegerField(),
            'page': serializers.IntegerField(),
            'pages': serializers.IntegerField(),
            'facets': serializers.DictField(),
            'relaxations': serializers.ListField(child=serializers.CharField()),
        })}
    )
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)

        candidates_qs = visible_candidates_for(company)
        facets = compute_pool_facets(candidates_qs)

        filtered_qs = filter_candidate_profiles(candidates_qs, request.query_params)

        shortlisted_user_ids = set(
            Shortlist.objects.filter(position=position).values_list('candidate_id', flat=True)
        )

        pool_items = []
        for candidate in filtered_qs:
            score_data = calculate_match_score(candidate, position)
            pool_items.append({
                'talent': TalentShortSerializer(candidate).data,
                'score': score_data['total_score'],
                'components': score_data['components'],
                'reasons': score_data['reasons'],
                'gaps': score_data.get('gaps', []),
                'shortlisted': candidate.user_id in shortlisted_user_ids,
            })

        # Sort by total score descending
        pool_items.sort(key=lambda x: x['score'], reverse=True)

        try:
            page = int(request.query_params.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        try:
            size = int(request.query_params.get('size', request.query_params.get('page_size', 20)))
        except (ValueError, TypeError):
            size = 20

        total = len(pool_items)
        pages = max(1, (total + size - 1) // size) if total > 0 else 1
        start = (page - 1) * size
        end = start + size
        page_items = pool_items[start:end]

        return Response({
            'items': page_items,
            'total': total,
            'page': page,
            'pages': pages,
            'facets': facets,
            'relaxations': [],
        })


class PositionShortlistListView(views.APIView):
    """List shortlisted talent for a position."""
    permission_classes = [IsEmployer]
    serializer_class = TalentShortSerializer

    @extend_schema(responses={200: TalentShortSerializer(many=True)})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError('not_found', 'Not found', 'Position not found', 404)

        shortlists = Shortlist.objects.filter(position=position).select_related('candidate__candidate_profile')
        candidates = []
        for s in shortlists:
            profile = getattr(s.candidate, 'candidate_profile', None)
            if profile and is_candidate_visible_to_company(profile, company):
                candidates.append(profile)

        items = [TalentShortSerializer(c).data for c in candidates]
        return Response(items)


class PositionShortlistView(views.APIView):
    permission_classes = [IsEmployer]

    @extend_schema(request=None, responses={204: None})
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


class PositionParseView(views.APIView):
    """Parse a job description into a position draft."""
    permission_classes = [IsEmployer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'resume'

    @extend_schema(
        request=JdParseRequestSerializer,
        responses={200: JdParseResultSerializer},
    )
    def post(self, request):
        serializer = JdParseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                'validation_failed',
                'Validation failed',
                errors=serializer.errors,
                status_code=422,
            )

        text = serializer.validated_data['text']
        import re
        lower_text = text.lower()

        specialization = 'backend'
        if 'frontend' in lower_text or 'react' in lower_text or 'vue' in lower_text:
            specialization = 'frontend'
        elif 'ml' in lower_text or 'data science' in lower_text or 'machine learning' in lower_text:
            specialization = 'ml_data'

        grades = []
        if 'intern' in lower_text or 'стажер' in lower_text:
            grades.append('intern')
        if 'junior' in lower_text or 'джуниор' in lower_text:
            grades.append('junior')
        if 'middle' in lower_text or 'мидл' in lower_text:
            grades.append('middle')
        if 'senior' in lower_text or 'сеньор' in lower_text or 'лид' in lower_text:
            grades.append('senior')
        if not grades:
            grades = ['middle']

        known_skills = {
            'python': 'python',
            'django': 'django',
            'fastapi': 'fastapi',
            'postgresql': 'postgresql',
            'postgres': 'postgresql',
            'docker': 'docker',
            'react': 'react',
            'typescript': 'typescript',
            'sql': 'sql',
            'algorithms': 'algorithms',
            'pytorch': 'pytorch',
        }
        found_skills = set()
        for kw, skill_id in known_skills.items():
            if re.search(r'\b' + re.escape(kw) + r'\b', lower_text):
                found_skills.add(skill_id)

        must_skills = sorted(found_skills)
        nice_skills = []

        formats = []
        if 'remote' in lower_text or 'удален' in lower_text or 'удалён' in lower_text:
            formats.append('remote')
        if 'hybrid' in lower_text or 'гибрид' in lower_text:
            formats.append('hybrid')
        if 'office' in lower_text or 'офис' in lower_text:
            formats.append('office')
        if not formats:
            formats = ['remote']

        salary_min = None
        salary_max = None
        range_match = re.search(r'(?:от\s*)?(\d+[\d\s]*\d+)\s*(?:до|-|–|—)\s*(\d+[\d\s]*\d+)\s*(?:руб|rub|₽)?', lower_text)
        if range_match:
            n1 = int(re.sub(r'\s+', '', range_match.group(1)))
            n2 = int(re.sub(r'\s+', '', range_match.group(2)))
            salary_min, salary_max = min(n1, n2), max(n1, n2)
        else:
            sal_matches = re.findall(r'(\d+[\d\s]*\d+)\s*(?:руб|rub|₽)', lower_text)
            if sal_matches:
                nums = [int(re.sub(r'\s+', '', m)) for m in sal_matches]
                if len(nums) == 1:
                    salary_min = nums[0]
                elif len(nums) >= 2:
                    salary_min, salary_max = min(nums[0], nums[1]), max(nums[0], nums[1])

        title = text.strip().split('\n')[0][:100] if text.strip() else 'Software Engineer'

        draft = {
            'title': title,
            'specialization': specialization,
            'grades': grades,
            'must_skills': must_skills,
            'nice_skills': nice_skills,
            'work_formats': formats,
            'location': 'Москва' if 'москв' in lower_text else '',
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_type': 'gross',
            'team_context': '',
            'description': text[:1000],
        }

        result = {
            'draft': draft,
            'unknown_terms': [],
            'blueprint': [],
            'source': 'rules',
        }
        return Response(result)


class TalentSearchView(views.APIView):
    """General talent search without a specific position."""
    permission_classes = [IsEmployer]
    serializer_class = TalentShortSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter('grades', str, description='Comma-separated grades, e.g. junior,middle'),
            OpenApiParameter('skills', str, description='Comma-separated skill IDs or names'),
            OpenApiParameter('fsp', str, description='true/false filter for FSP achievements'),
            OpenApiParameter('formats', str, description='Comma-separated work formats: remote,hybrid,office'),
            OpenApiParameter('salary_max', int, description='Max salary expectations'),
            OpenApiParameter('confirmed_only', str, description='true to show only verified league grades'),
            OpenApiParameter('preset', str, description='Preset filter: fsp_stars, confirmed'),
            OpenApiParameter('page', int, description='Page number (default 1)'),
            OpenApiParameter('size', int, description='Page size (default 20)'),
        ],
        responses={200: inline_serializer('TalentSearchResponse', fields={
            'items': TalentShortSerializer(many=True),
            'total': serializers.IntegerField(),
            'page': serializers.IntegerField(),
            'pages': serializers.IntegerField(),
            'facets': serializers.DictField(),
        })}
    )
    def get(self, request):
        company = get_employer_company(request.user)
        candidates_qs = visible_candidates_for(company)
        facets = compute_pool_facets(candidates_qs)

        filtered_qs = filter_candidate_profiles(candidates_qs, request.query_params)

        try:
            page = int(request.query_params.get('page', 1))
        except (ValueError, TypeError):
            page = 1
        try:
            size = int(request.query_params.get('size', request.query_params.get('page_size', 20)))
        except (ValueError, TypeError):
            size = 20

        total = filtered_qs.count()
        pages = max(1, (total + size - 1) // size) if total > 0 else 1
        start = (page - 1) * size
        end = start + size
        paged_candidates = filtered_qs[start:end]

        items = [TalentShortSerializer(c).data for c in paged_candidates]
        return Response({
            'items': items,
            'total': total,
            'page': page,
            'pages': pages,
            'facets': facets,
        })


class TalentDetailView(views.APIView):
    """Talent card view for employers.

    SECURITY INVARIANT: Only visible candidates are shown.
    Contacts are only unmasked if an active ContactGrant exists!
    """
    permission_classes = [IsEmployer]

    @extend_schema(responses={200: inline_serializer('TalentDetailResponse', fields={
        'public_id': serializers.CharField(),
        'display_name': serializers.CharField(),
        'city': serializers.CharField(),
        'work_formats': serializers.ListField(child=serializers.CharField()),
        'salary_min': serializers.IntegerField(allow_null=True),
        'salary_max': serializers.IntegerField(allow_null=True),
        'salary_type': serializers.CharField(),
        'league': serializers.DictField(allow_null=True),
        'fsp': serializers.DictField(),
        'skills': serializers.ListField(child=serializers.DictField()),
        'verified_topics': serializers.ListField(child=serializers.CharField()),
        'topics': serializers.ListField(child=serializers.DictField()),
        'fsp_results': serializers.ListField(child=serializers.DictField()),
        'assessments': serializers.ListField(child=serializers.DictField()),
        'integrity_flags': serializers.ListField(child=serializers.CharField()),
        'about': serializers.CharField(),
        'experience_text': serializers.CharField(),
        'contacts': serializers.DictField(allow_null=True),
    })})
    def get(self, request, public_id):
        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        company = get_employer_company(request.user)

        if not is_candidate_visible_to_company(profile, company):
            raise FSPAPIError('not_found', 'Not found', 'Candidate not found', 404)

        data = TalentShortSerializer(profile).data
        data['about'] = profile.about
        data['experience_text'] = profile.experience_text

        from assessment.models import AssessmentItem
        from core.enums import AssessmentStatus
        passed_topics = set(AssessmentItem.objects.filter(
            assessment__candidate=profile.user,
            assessment__status=AssessmentStatus.FINISHED,
            correct=True,
        ).values_list('family__topic', flat=True).distinct())

        all_topics = set(AssessmentItem.objects.filter(
            assessment__candidate=profile.user,
            assessment__status=AssessmentStatus.FINISHED,
        ).values_list('family__topic', flat=True).distinct())

        topics_data = []
        for t in all_topics:
            if not t:
                continue
            topics_data.append({
                'topic': t,
                'level': 'strong' if t in passed_topics else 'moderate',
            })
        data['topics'] = topics_data

        fsp_results = []
        for r in profile.user.fsp_results.all().order_by('-date')[:10]:
            fsp_results.append({
                'event_id': r.event_id,
                'event_name': r.event_name,
                'date': r.date.isoformat(),
                'discipline': r.discipline,
                'stage': r.stage,
                'format': r.format,
                'team_size': r.team_size,
                'placement': r.placement,
                'tier': r.tier,
                'participants_total': r.participants_total,
            })
        data['fsp_results'] = fsp_results

        assessments_data = []
        for a in profile.user.assessments.filter(status=AssessmentStatus.FINISHED).order_by('-finished_at')[:10]:
            assessments_data.append({
                'id': str(a.id),
                'kind': a.kind,
                'finished_at': a.finished_at.isoformat() if a.finished_at else '',
                'rating': a.rating or 1000,
                'result_grade': a.result_grade or a.claimed_grade,
            })
        data['assessments'] = assessments_data
        data['integrity_flags'] = []

        # Always attempt contact access so denials are audit-logged
        try:
            contacts = ContactAccessService.get_contacts(
                company.id, profile.user_id, actor_id=request.user.id
            )
            data['contacts'] = {
                'full_name': contacts.full_name,
                'email': contacts.email,
                'phone': contacts.phone,
                'telegram': contacts.telegram,
            }
        except Exception:
            data['contacts'] = None

        return Response(data)
