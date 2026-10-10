"""Matching app API views."""

import logging
from core.errors import ContactNotGranted, FSPAPIError
from core.pagination import FSPPagination, PaginationQuerySerializer
from core.permissions import IsEmployer
from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from identity.models import AuditLog
from outreach.services import ContactAccessService
from profiles.models import CandidateProfile
from profiles.selectors import is_candidate_visible_to_company
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from matching.models import Company, CompanyMember, Position, Shortlist
from matching.serializers import (
    CompanyMinimalSerializer,
    CompanySearchQuerySerializer,
    CompanySerializer,
    JdParseRequestSerializer,
    JdParseResultSerializer,
    PositionSerializer,
    TalentShortSerializer,
)
from matching.services import get_position_pool, search_talent

logger = logging.getLogger(__name__)


def get_employer_company(user):
    """Retrieve the company for an employer user. Raises 403 if no membership."""
    membership = user.company_memberships.select_related("company").first()
    if membership:
        return membership.company
    raise FSPAPIError(
        "company_required",
        "Company required",
        "Create or join a company before performing employer actions.",
        403,
    )


class CompanyListCreateView(views.APIView):
    serializer_class = CompanySerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsEmployer()]
        return [permissions.IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="search",
                description="Search companies by name for candidate blocklist (min length 2)",
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name="page", type=int, required=False, description="Page number (default 1)"
            ),
            OpenApiParameter(
                name="size", type=int, required=False, description="Page size (default 20, max 100)"
            ),
        ],
        responses={
            200: inline_serializer(
                "CompanyPaginatedResponse",
                fields={
                    "items": CompanyMinimalSerializer(many=True),
                    "total": serializers.IntegerField(),
                    "page": serializers.IntegerField(),
                    "pages": serializers.IntegerField(),
                },
            )
        },
    )
    def get(self, request):
        query_serializer = CompanySearchQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=query_serializer.errors,
                status_code=422,
            )
        params = query_serializer.validated_data
        search = params["search"].strip()
        qs = Company.objects.filter(name__icontains=search).order_by("name", "id")

        paginator = FSPPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            serializer = CompanyMinimalSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = CompanyMinimalSerializer(qs, many=True)
        return Response(
            {
                "items": serializer.data,
                "total": len(serializer.data),
                "page": 1,
                "pages": 1,
            }
        )

    @extend_schema(
        request=CompanySerializer,
        responses={201: CompanySerializer},
    )
    def post(self, request):
        if request.user.company_memberships.exists():
            raise FSPAPIError(
                "company_already_exists",
                "Company already exists",
                "You are already associated with a company.",
                status_code=400,
            )
        serializer = CompanySerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )
        try:
            with transaction.atomic():
                company = serializer.save()
                CompanyMember.objects.create(company=company, user=request.user)
        except IntegrityError:
            raise FSPAPIError(
                "company_already_exists",
                "Company already exists",
                "You are already associated with a company.",
                status_code=400,
            )
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
            raise FSPAPIError(
                "validation_failed", "Validation failed", errors=serializer.errors, status_code=422
            )
        serializer.save()
        return Response(serializer.data)


class PositionListCreateView(views.APIView):
    permission_classes = [IsEmployer]
    serializer_class = PositionSerializer

    @extend_schema(responses={200: PositionSerializer(many=True)})
    def get(self, request):
        company = get_employer_company(request.user)
        positions = Position.objects.filter(company=company).order_by("-created_at")
        return Response(PositionSerializer(positions, many=True).data)

    @extend_schema(request=PositionSerializer, responses={201: PositionSerializer})
    def post(self, request):
        company = get_employer_company(request.user)
        serializer = PositionSerializer(data=request.data)
        if not serializer.is_valid():
            is_salary_err = any(
                k in serializer.errors for k in ("salary_min", "salary_max", "salary_type")
            )
            err_code = "salary_invalid" if is_salary_err else "validation_failed"
            raise FSPAPIError(
                err_code, "Validation failed", errors=serializer.errors, status_code=422
            )
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
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)
        return Response(PositionSerializer(position).data)

    @extend_schema(request=PositionSerializer, responses={200: PositionSerializer})
    def put(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)
        serializer = PositionSerializer(position, data=request.data, partial=True)
        if not serializer.is_valid():
            is_salary_err = any(
                k in serializer.errors for k in ("salary_min", "salary_max", "salary_type")
            )
            err_code = "salary_invalid" if is_salary_err else "validation_failed"
            raise FSPAPIError(
                err_code, "Validation failed", errors=serializer.errors, status_code=422
            )
        serializer.save()
        return Response(PositionSerializer(position).data)


class PositionPoolView(views.APIView):
    """Scouted talent pool for a position with explainable scores and reason chips."""

    permission_classes = [IsEmployer]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "grades", str, description="Comma-separated grades, e.g. junior,middle"
            ),
            OpenApiParameter("skills", str, description="Comma-separated skill IDs or names"),
            OpenApiParameter("fsp", str, description="true/false filter for FSP achievements"),
            OpenApiParameter(
                "formats", str, description="Comma-separated work formats: remote,hybrid,office"
            ),
            OpenApiParameter("salary_max", int, description="Max salary expectations"),
            OpenApiParameter(
                "confirmed_only", str, description="true to show only verified league grades"
            ),
            OpenApiParameter("preset", str, description="Preset filter: fsp_stars, confirmed"),
            OpenApiParameter("page", int, description="Page number (default 1)"),
            OpenApiParameter("size", int, description="Page size (default 20)"),
        ],
        responses={
            200: inline_serializer(
                "PositionPoolResponse",
                fields={
                    "items": serializers.ListField(
                        child=inline_serializer(
                            "PoolItem",
                            fields={
                                "talent": TalentShortSerializer(),
                                "score": serializers.FloatField(),
                                "components": serializers.ListField(
                                    child=inline_serializer(
                                        "PoolComponent",
                                        fields={
                                            "key": serializers.CharField(),
                                            "value": serializers.FloatField(),
                                            "weight": serializers.FloatField(),
                                            "contribution": serializers.FloatField(),
                                        },
                                    )
                                ),
                                "reasons": serializers.ListField(child=serializers.DictField()),
                                "gaps": serializers.ListField(child=serializers.CharField()),
                                "shortlisted": serializers.BooleanField(),
                            },
                        )
                    ),
                    "total": serializers.IntegerField(),
                    "page": serializers.IntegerField(),
                    "pages": serializers.IntegerField(),
                    "facets": serializers.DictField(),
                    "relaxations": serializers.ListField(child=serializers.CharField()),
                },
            )
        },
    )
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        pagination_serializer = PaginationQuerySerializer(data=request.query_params)
        if not pagination_serializer.is_valid():
            raise FSPAPIError(
                code="validation_failed",
                title="Validation failed",
                detail="Invalid pagination parameters",
                status_code=422,
                errors=pagination_serializer.errors,
            )
        page = pagination_serializer.validated_data["page"]
        size = pagination_serializer.validated_data["size"]

        result = get_position_pool(
            position=position,
            company=company,
            query_params=request.query_params,
            page=page,
            size=size,
        )
        return Response(result)


class PositionShortlistListView(views.APIView):
    """List shortlisted talent for a position."""

    permission_classes = [IsEmployer]
    serializer_class = TalentShortSerializer

    @extend_schema(responses={200: TalentShortSerializer(many=True)})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        shortlists = Shortlist.objects.filter(position=position).select_related(
            "candidate__candidate_profile"
        )
        candidates = []
        for s in shortlists:
            profile = getattr(s.candidate, "candidate_profile", None)
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
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile or not is_candidate_visible_to_company(profile, company):
            raise FSPAPIError("not_found", "Not found", "Candidate not found", 404)

        Shortlist.objects.get_or_create(position=position, candidate=profile.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={204: None})
    def delete(self, request, pk, public_id):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError("not_found", "Not found", "Candidate not found", 404)

        Shortlist.objects.filter(position=position, candidate=profile.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PositionParseView(views.APIView):
    """Parse a job description into a position draft."""

    permission_classes = [IsEmployer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jd_parse"

    @extend_schema(
        request=JdParseRequestSerializer,
        responses={200: JdParseResultSerializer},
    )
    def post(self, request):
        serializer = JdParseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        text = serializer.validated_data["text"]

        try:
            from matching.tasks import parse_jd_task

            async_res = parse_jd_task.apply_async(args=[text], queue="llm")
            res_dict = async_res.get(timeout=15)
            # Ensure draft fallback defaults
            draft = res_dict.get("draft") or {}
            if not draft.get("salary_type"):
                draft["salary_type"] = "gross"
            res_dict["draft"] = draft
            return Response(res_dict)
        except Exception as celery_err:
            logger.warning(
                "Celery parse_jd failed or timed out (%s), falling back to rules",
                type(celery_err).__name__,
            )
            try:
                from llm_gateway import FakeLlm, parse_jd

                result = parse_jd(text, gateway=FakeLlm())
                draft = result.draft
                if not draft.get("salary_type"):
                    draft["salary_type"] = "gross"
                return Response(
                    {
                        "draft": draft,
                        "unknown_terms": result.unknown_terms,
                        "blueprint": result.blueprint,
                        "source": result.source,
                    }
                )
            except Exception as e:
                logger.exception("Failed to parse JD with rules fallback: %s", e)
                raise FSPAPIError(
                    "jd_parse_failed",
                    "Failed to parse job description",
                    "Please fill the position manually or try again later.",
                    500,
                ) from None


class TalentSearchView(views.APIView):
    """General talent search without a specific position."""

    permission_classes = [IsEmployer]
    serializer_class = TalentShortSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "grades", str, description="Comma-separated grades, e.g. junior,middle"
            ),
            OpenApiParameter("skills", str, description="Comma-separated skill IDs or names"),
            OpenApiParameter("fsp", str, description="true/false filter for FSP achievements"),
            OpenApiParameter(
                "formats", str, description="Comma-separated work formats: remote,hybrid,office"
            ),
            OpenApiParameter("salary_max", int, description="Max salary expectations"),
            OpenApiParameter(
                "confirmed_only", str, description="true to show only verified league grades"
            ),
            OpenApiParameter("preset", str, description="Preset filter: fsp_stars, confirmed"),
            OpenApiParameter("page", int, description="Page number (default 1)"),
            OpenApiParameter("size", int, description="Page size (default 20)"),
        ],
        responses={
            200: inline_serializer(
                "TalentSearchResponse",
                fields={
                    "items": TalentShortSerializer(many=True),
                    "total": serializers.IntegerField(),
                    "page": serializers.IntegerField(),
                    "pages": serializers.IntegerField(),
                    "facets": serializers.DictField(),
                },
            )
        },
    )
    def get(self, request):
        company = get_employer_company(request.user)

        pagination_serializer = PaginationQuerySerializer(data=request.query_params)
        if not pagination_serializer.is_valid():
            raise FSPAPIError(
                code="validation_failed",
                title="Validation failed",
                detail="Invalid pagination parameters",
                status_code=422,
                errors=pagination_serializer.errors,
            )
        page = pagination_serializer.validated_data["page"]
        size = pagination_serializer.validated_data["size"]

        result = search_talent(
            company=company,
            query_params=request.query_params,
            page=page,
            size=size,
        )
        return Response(result)


class TalentDetailView(views.APIView):
    """Talent card view for employers.

    SECURITY INVARIANT: Only visible candidates are shown.
    Contacts are only unmasked if an active ContactGrant exists!
    """

    permission_classes = [IsEmployer]

    @extend_schema(
        responses={
            200: inline_serializer(
                "TalentDetailResponse",
                fields={
                    "public_id": serializers.CharField(),
                    "display_name": serializers.CharField(),
                    "city": serializers.CharField(),
                    "work_formats": serializers.ListField(child=serializers.CharField()),
                    "salary_min": serializers.IntegerField(allow_null=True),
                    "salary_max": serializers.IntegerField(allow_null=True),
                    "salary_type": serializers.CharField(),
                    "league": serializers.DictField(allow_null=True),
                    "fsp": serializers.DictField(),
                    "skills": serializers.ListField(child=serializers.DictField()),
                    "verified_topics": serializers.ListField(child=serializers.CharField()),
                    "topics": serializers.ListField(child=serializers.DictField()),
                    "fsp_results": serializers.ListField(child=serializers.DictField()),
                    "assessments": serializers.ListField(child=serializers.DictField()),
                    "integrity_flags": serializers.ListField(child=serializers.CharField()),
                    "about": serializers.CharField(),
                    "experience_text": serializers.CharField(),
                    "contacts": serializers.DictField(allow_null=True),
                },
            )
        }
    )
    def get(self, request, public_id):
        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError("not_found", "Not found", "Candidate not found", 404)

        company = get_employer_company(request.user)

        if not is_candidate_visible_to_company(profile, company):
            AuditLog.objects.create(
                actor_id=request.user.id,
                action="talent_card_access_denied",
                target_type="CandidateProfile",
                target_id=str(profile.user_id),
                meta={
                    "company_id": str(company.id),
                    "public_id": public_id,
                    "reason": "candidate_not_visible",
                },
            )
            raise FSPAPIError("not_found", "Not found", "Candidate not found", 404)

        data = TalentShortSerializer(profile).data
        data["about"] = profile.about
        data["experience_text"] = profile.experience_text

        from assessment.models import AssessmentItem
        from core.enums import AssessmentStatus

        passed_topics = set(
            AssessmentItem.objects.filter(
                assessment__candidate=profile.user,
                assessment__status=AssessmentStatus.FINISHED,
                correct=True,
            )
            .values_list("family__topic", flat=True)
            .distinct()
        )

        all_topics = set(
            AssessmentItem.objects.filter(
                assessment__candidate=profile.user,
                assessment__status=AssessmentStatus.FINISHED,
            )
            .values_list("family__topic", flat=True)
            .distinct()
        )

        topics_data = []
        for t in all_topics:
            if not t:
                continue
            topics_data.append(
                {
                    "topic": t,
                    "level": "strong" if t in passed_topics else "moderate",
                }
            )
        data["topics"] = topics_data

        fsp_results = []
        for r in profile.user.fsp_results.all().order_by("-date")[:10]:
            fsp_results.append(
                {
                    "event_id": r.event_id,
                    "event_name": r.event_name,
                    "date": r.date.isoformat(),
                    "discipline": r.discipline,
                    "stage": r.stage,
                    "format": r.format,
                    "team_size": r.team_size,
                    "placement": r.placement,
                    "tier": r.tier,
                    "participants_total": r.participants_total,
                }
            )
        data["fsp_results"] = fsp_results

        assessments_data = []
        for a in profile.user.assessments.filter(status=AssessmentStatus.FINISHED).order_by(
            "-finished_at"
        )[:10]:
            assessments_data.append(
                {
                    "id": a.public_id,
                    "public_id": a.public_id,
                    "kind": a.kind,
                    "finished_at": a.finished_at.isoformat() if a.finished_at else "",
                    "rating": a.rating or 1000,
                    "result_grade": a.result_grade or a.claimed_grade,
                    "decision": a.decision,
                }
            )
        data["assessments"] = assessments_data
        data["integrity_flags"] = []

        # Always attempt contact access so denials are audit-logged
        try:
            contacts = ContactAccessService.get_contacts(
                company.id, profile.user_id, actor_id=request.user.id
            )
            data["contacts"] = {
                "full_name": contacts.full_name,
                "email": contacts.email,
                "phone": contacts.phone,
                "telegram": contacts.telegram,
            }
        except ContactNotGranted:
            data["contacts"] = None

        return Response(data)
