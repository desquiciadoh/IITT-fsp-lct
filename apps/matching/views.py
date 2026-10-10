"""Matching app API views."""

import logging

from core.enums import (
    ApplicationStatus,
    ContactGrantSource,
    MicroTaskFormat,
    PositionStatus,
)
from core.errors import ContactNotGranted, FSPAPIError
from core.pagination import FSPPagination, PaginationQuerySerializer
from core.permissions import IsCandidate, IsEmployer
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from identity.models import AuditLog
from outreach.models import ContactGrant
from outreach.services import ContactAccessService
from profiles.models import CandidateProfile
from profiles.pdf_service import generate_player_card_pdf
from profiles.selectors import is_candidate_visible_to_company
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from matching.models import (
    Application,
    ApplicationEvent,
    Company,
    CompanyMember,
    MicroTask,
    MicroTaskDrop,
    Position,
    Shortlist,
)
from matching.serializers import (
    ApplicationCandidateSerializer,
    ApplicationCreateSerializer,
    ApplicationEmployerSerializer,
    ApplicationStatusUpdateSerializer,
    CompanyMinimalSerializer,
    CompanySearchQuerySerializer,
    CompanySerializer,
    JdParseRequestSerializer,
    JdParseResultSerializer,
    MicroTaskCreateSerializer,
    MicroTaskDropCandidateSerializer,
    MicroTaskRateSerializer,
    MicroTaskSerializer,
    MicroTaskSubmissionEmployerSerializer,
    MicroTaskSubmitSerializer,
    PositionSerializer,
    TalentShortSerializer,
    VacancySerializer,
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
                import importlib

                gateway = importlib.import_module("llm_gateway")
                parse_jd_func = gateway.parse_jd
                fake_llm_cls = gateway.FakeLlm

                result = parse_jd_func(text, gateway=fake_llm_cls())
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


class TalentCardPdfView(views.APIView):
    """Employer view to export a watermarked player card PDF."""

    permission_classes = [IsEmployer]

    @extend_schema(
        responses={(200, "application/pdf"): bytes},
        description="Export watermarked candidate player card PDF for employer",
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
                    "export": "pdf",
                },
            )
            raise FSPAPIError("not_found", "Not found", "Candidate not found", 404)

        watermark_parts = [company.name]
        if company.inn:
            watermark_parts.append(f"ИНН {company.inn}")
        watermark_text = " · ".join(watermark_parts)

        AuditLog.objects.create(
            actor_id=request.user.id,
            action="talent_card_pdf_exported",
            target_type="CandidateProfile",
            target_id=str(profile.user_id),
            meta={
                "public_id": public_id,
                "company_id": str(company.id),
                "watermark": watermark_text,
            },
        )

        pdf_bytes = generate_player_card_pdf(profile, watermark=watermark_text)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="player_card_{profile.public_id}_{company.id}.pdf"'
        return response


class VacancyListView(views.APIView):
    """Public listing of published vacancies (Task BE-17)."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="vacancies_list",
        parameters=[
            OpenApiParameter("specialization", str, description="Specialization filter"),
            OpenApiParameter("grades", str, description="Comma-separated grades"),
            OpenApiParameter("work_formats", str, description="Comma-separated work formats"),
            OpenApiParameter("salary_min", int, description="Minimum salary"),
            OpenApiParameter("salary_max", int, description="Maximum salary"),
            OpenApiParameter("search", str, description="Text search in title/description"),
            OpenApiParameter("page", int, description="Page number (default 1)"),
            OpenApiParameter("size", int, description="Page size (default 20)"),
        ],
        responses={
            200: inline_serializer(
                "VacancyListResponse",
                fields={
                    "items": VacancySerializer(many=True),
                    "total": serializers.IntegerField(),
                    "page": serializers.IntegerField(),
                    "pages": serializers.IntegerField(),
                },
            )
        },
    )
    def get(self, request):
        qs = (
            Position.objects.filter(
                is_public=True,
                status=PositionStatus.OPEN,
            )
            .select_related("company")
            .order_by("-created_at")
        )

        spec = request.query_params.get("specialization")
        if spec:
            qs = qs.filter(specialization=spec)

        grades_param = request.query_params.get("grades")
        if grades_param:
            grades = [g.strip() for g in grades_param.split(",") if g.strip()]
            if grades:
                qs = qs.filter(grades__overlap=grades)

        formats_param = request.query_params.get("work_formats")
        if formats_param:
            formats = [f.strip() for f in formats_param.split(",") if f.strip()]
            if formats:
                qs = qs.filter(work_formats__overlap=formats)

        salary_min = request.query_params.get("salary_min")
        if salary_min:
            try:
                qs = qs.filter(salary_max__gte=int(salary_min))
            except ValueError:
                pass

        salary_max = request.query_params.get("salary_max")
        if salary_max:
            try:
                qs = qs.filter(salary_min__lte=int(salary_max))
            except ValueError:
                pass

        search = request.query_params.get("search")
        if search:
            from django.db.models import Q

            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

        total = qs.count()

        pagination_serializer = PaginationQuerySerializer(data=request.query_params)
        page = 1
        size = 20
        if pagination_serializer.is_valid():
            page = pagination_serializer.validated_data["page"]
            size = pagination_serializer.validated_data["size"]

        start = (page - 1) * size
        end = start + size
        items = qs[start:end]
        pages = (total + size - 1) // size if size > 0 else 1

        return Response(
            {
                "items": VacancySerializer(items, many=True).data,
                "total": total,
                "page": page,
                "pages": pages,
            }
        )


class VacancyDetailView(views.APIView):
    """Public vacancy detail view (Task BE-17)."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(responses={200: VacancySerializer})
    def get(self, request, pk):
        vacancy = (
            Position.objects.filter(
                id=pk,
                is_public=True,
                status=PositionStatus.OPEN,
            )
            .select_related("company")
            .first()
        )
        if not vacancy:
            raise FSPAPIError("not_found", "Not found", "Vacancy not found", 404)
        return Response(VacancySerializer(vacancy).data)


class ApplyVacancyView(views.APIView):
    """Candidate submits a direct application to a vacancy (Task BE-17).

    INVARIANT: Atomic creation of Application and ContactGrant.
    Candidate contacts become accessible to the employer upon application.
    """

    permission_classes = [IsCandidate]

    @extend_schema(
        request=ApplicationCreateSerializer,
        responses={201: ApplicationCandidateSerializer},
    )
    def post(self, request, pk):
        vacancy = (
            Position.objects.filter(
                id=pk,
                is_public=True,
                status=PositionStatus.OPEN,
            )
            .select_related("company")
            .first()
        )
        if not vacancy:
            raise FSPAPIError("not_found", "Not found", "Vacancy not found", 404)

        if Application.objects.filter(position=vacancy, candidate=request.user).exists():
            raise FSPAPIError(
                "already_applied",
                "Already applied",
                "You have already applied to this vacancy.",
                status_code=409,
            )

        serializer = ApplicationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        note = serializer.validated_data.get("note", "")

        with transaction.atomic():
            application = Application.objects.create(
                position=vacancy,
                candidate=request.user,
                note=note,
                status=ApplicationStatus.APPLIED,
            )
            ApplicationEvent.objects.create(
                application=application,
                from_status="",
                to_status=ApplicationStatus.APPLIED,
                actor=request.user,
            )
            ContactGrant.objects.get_or_create(
                candidate=request.user,
                company=vacancy.company,
                source=ContactGrantSource.APPLICATION,
                defaults={
                    "source_id": application.id,
                },
            )

        return Response(
            ApplicationCandidateSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


class CandidateApplicationListView(views.APIView):
    """List of candidate's own applications (Task BE-17)."""

    permission_classes = [IsCandidate]

    @extend_schema(responses={200: ApplicationCandidateSerializer(many=True)})
    def get(self, request):
        applications = (
            Application.objects.filter(candidate=request.user)
            .select_related("position__company")
            .order_by("-created_at")
        )
        return Response(ApplicationCandidateSerializer(applications, many=True).data)


class CandidateApplicationWithdrawView(views.APIView):
    """Candidate withdraws their application (Task BE-17)."""

    permission_classes = [IsCandidate]
    serializer_class = ApplicationCandidateSerializer

    @extend_schema(request=None, responses={200: ApplicationCandidateSerializer})
    def post(self, request, pk):
        application = (
            Application.objects.filter(id=pk, candidate=request.user)
            .select_related("position__company")
            .first()
        )
        if not application:
            raise FSPAPIError("not_found", "Not found", "Application not found", 404)

        if application.status in [
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.REJECTED,
            ApplicationStatus.HIRED,
        ]:
            raise FSPAPIError(
                "invalid_transition",
                "Invalid status transition",
                f"Cannot withdraw application in status '{application.status}'.",
                status_code=422,
            )

        old_status = application.status
        with transaction.atomic():
            application.status = ApplicationStatus.WITHDRAWN
            application.save(update_fields=["status", "updated_at"])
            ApplicationEvent.objects.create(
                application=application,
                from_status=old_status,
                to_status=ApplicationStatus.WITHDRAWN,
                actor=request.user,
            )

        return Response(ApplicationCandidateSerializer(application).data)


class PositionApplicationListView(views.APIView):
    """Employer view of applications for a specific position (Task BE-17)."""

    permission_classes = [IsEmployer]

    @extend_schema(responses={200: ApplicationEmployerSerializer(many=True)})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        applications = (
            Application.objects.filter(position=position)
            .select_related("candidate__candidate_profile")
            .prefetch_related(
                "candidate__league_memberships",
                "candidate__fsp_results",
                "candidate__candidate_profile__skills__skill",
            )
            .order_by("-created_at")
        )
        return Response(ApplicationEmployerSerializer(applications, many=True).data)


class PositionApplicationStatusView(views.APIView):
    """Employer updates candidate application status in pipeline (Task BE-17)."""

    permission_classes = [IsEmployer]

    @extend_schema(
        request=ApplicationStatusUpdateSerializer,
        responses={200: ApplicationEmployerSerializer},
    )
    def patch(self, request, position_pk, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=position_pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        application = (
            Application.objects.filter(id=pk, position=position)
            .select_related("candidate__candidate_profile")
            .first()
        )
        if not application:
            raise FSPAPIError("not_found", "Not found", "Application not found", 404)

        serializer = ApplicationStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        new_status = serializer.validated_data["status"]
        old_status = application.status

        # Valid transitions:
        # applied -> reviewing, invited, rejected
        # reviewing -> invited, rejected
        # invited -> hired, rejected
        valid_transitions = {
            ApplicationStatus.APPLIED: [
                ApplicationStatus.REVIEWING,
                ApplicationStatus.INVITED,
                ApplicationStatus.REJECTED,
            ],
            ApplicationStatus.REVIEWING: [
                ApplicationStatus.INVITED,
                ApplicationStatus.REJECTED,
            ],
            ApplicationStatus.INVITED: [
                ApplicationStatus.HIRED,
                ApplicationStatus.REJECTED,
            ],
        }

        if new_status not in valid_transitions.get(old_status, []):
            raise FSPAPIError(
                "invalid_transition",
                "Invalid status transition",
                f"Cannot transition application from '{old_status}' to '{new_status}'.",
                status_code=422,
            )

        with transaction.atomic():
            application.status = new_status
            application.save(update_fields=["status", "updated_at"])
            ApplicationEvent.objects.create(
                application=application,
                from_status=old_status,
                to_status=new_status,
                actor=request.user,
            )

        return Response(ApplicationEmployerSerializer(application).data)


# ---------------------------------------------------------------------------
# Task BE-18: Micro-Tasks Views
# ---------------------------------------------------------------------------


class MicroTaskListCreateView(views.APIView):
    """Employer lists or creates company micro-tasks (Task BE-18)."""

    permission_classes = [IsEmployer]

    @extend_schema(responses={200: MicroTaskSerializer(many=True)})
    def get(self, request):
        company = get_employer_company(request.user)
        tasks = MicroTask.objects.filter(company=company).order_by("-created_at")
        return Response(MicroTaskSerializer(tasks, many=True).data)

    @extend_schema(
        request=MicroTaskCreateSerializer,
        responses={201: MicroTaskSerializer},
    )
    def post(self, request):
        company = get_employer_company(request.user)
        serializer = MicroTaskCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        task = serializer.save(company=company)
        return Response(MicroTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class MicroTaskDetailView(views.APIView):
    """Employer retrieves or deletes a micro-task (Task BE-18)."""

    permission_classes = [IsEmployer]

    @extend_schema(responses={200: MicroTaskSerializer})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        task = MicroTask.objects.filter(id=pk, company=company).first()
        if not task:
            raise FSPAPIError("not_found", "Not found", "Micro-task not found", 404)
        return Response(MicroTaskSerializer(task).data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        company = get_employer_company(request.user)
        task = MicroTask.objects.filter(id=pk, company=company).first()
        if not task:
            raise FSPAPIError("not_found", "Not found", "Micro-task not found", 404)
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CandidateMicroTaskListView(views.APIView):
    """Candidate lists their assigned micro-task drops (Task BE-18)."""

    permission_classes = [IsCandidate]

    @extend_schema(responses={200: MicroTaskDropCandidateSerializer(many=True)})
    def get(self, request):
        drops = (
            MicroTaskDrop.objects.filter(candidate=request.user)
            .select_related("task__company")
            .order_by("-dropped_at")
        )
        return Response(MicroTaskDropCandidateSerializer(drops, many=True).data)


class CandidateMicroTaskSubmitView(views.APIView):
    """Candidate submits a solution to an assigned micro-task drop (Task BE-18)."""

    permission_classes = [IsCandidate]

    @extend_schema(
        request=MicroTaskSubmitSerializer,
        responses={200: MicroTaskDropCandidateSerializer},
    )
    def post(self, request, drop_id):
        drop = (
            MicroTaskDrop.objects.filter(id=drop_id, candidate=request.user)
            .select_related("task")
            .first()
        )
        if not drop:
            raise FSPAPIError("not_found", "Not found", "Micro-task drop not found", 404)

        if drop.submitted_at is not None:
            raise FSPAPIError(
                "already_submitted",
                "Already submitted",
                "You have already submitted this micro-task.",
                status_code=422,
            )

        serializer = MicroTaskSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        answer = serializer.validated_data["answer"]
        task = drop.task

        # Grading logic
        score = None
        if task.format == MicroTaskFormat.AUTO:
            if task.key is not None:
                # Deterministic check against secret key
                if isinstance(task.key, dict) and isinstance(answer, dict):
                    score = 1.0 if answer == task.key else 0.0
                elif str(answer).strip() == str(task.key).strip():
                    score = 1.0
                else:
                    score = 0.0
            else:
                score = 1.0  # default passing if no key configured
        elif task.format == MicroTaskFormat.OPEN:
            score = None  # awaiting employer review

        from assessment.services import get_current_time_for_user

        now = get_current_time_for_user(request.user)
        if task.deadline and now > task.deadline:
            raise FSPAPIError(
                "deadline_passed",
                "Deadline passed",
                "The submission deadline for this micro-task has expired.",
                status_code=422,
            )

        drop.answer = answer
        drop.score = score
        drop.submitted_at = now
        drop.save(update_fields=["answer", "score", "submitted_at"])

        # Update candidate profile last_active_at (activity signal)
        profile = getattr(request.user, "candidate_profile", None)
        if profile:
            profile.last_active_at = now
            profile.save(update_fields=["last_active_at"])

        return Response(MicroTaskDropCandidateSerializer(drop).data)


class MicroTaskSubmissionsListView(views.APIView):
    """Employer views all candidate submissions for a micro-task (Task BE-18)."""

    permission_classes = [IsEmployer]

    @extend_schema(responses={200: MicroTaskSubmissionEmployerSerializer(many=True)})
    def get(self, request, pk):
        company = get_employer_company(request.user)
        task = MicroTask.objects.filter(id=pk, company=company).first()
        if not task:
            raise FSPAPIError("not_found", "Not found", "Micro-task not found", 404)

        submissions = (
            MicroTaskDrop.objects.filter(task=task, submitted_at__isnull=False)
            .select_related("candidate__candidate_profile")
            .order_by("-submitted_at")
        )
        return Response(MicroTaskSubmissionEmployerSerializer(submissions, many=True).data)


class MicroTaskRateSubmissionView(views.APIView):
    """Employer rates a candidate's micro-task submission (Task BE-18)."""

    permission_classes = [IsEmployer]

    @extend_schema(
        request=MicroTaskRateSerializer,
        responses={200: MicroTaskSubmissionEmployerSerializer},
    )
    def post(self, request, drop_id):
        company = get_employer_company(request.user)
        drop = (
            MicroTaskDrop.objects.filter(id=drop_id, task__company=company)
            .select_related("task", "candidate__candidate_profile")
            .first()
        )
        if not drop:
            raise FSPAPIError("not_found", "Not found", "Submission not found", 404)

        if drop.submitted_at is None:
            raise FSPAPIError(
                "not_submitted",
                "Not submitted",
                "Candidate has not submitted this micro-task yet.",
                status_code=422,
            )

        serializer = MicroTaskRateSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        rating = serializer.validated_data["employer_rating"]
        drop.employer_rating = rating
        drop.save(update_fields=["employer_rating"])
        return Response(MicroTaskSubmissionEmployerSerializer(drop).data)


class MicroTaskPrefillOfferView(views.APIView):
    """Prefills a Draft Offer from a candidate's micro-task submission (Task BE-18)."""

    permission_classes = [IsEmployer]

    @extend_schema(request=None, responses={200: inline_serializer("MicroTaskPrefillOfferResponse", fields={
        "candidate_id": serializers.CharField(),
        "candidate_public_id": serializers.CharField(),
        "candidate_name": serializers.CharField(),
        "company_id": serializers.CharField(),
        "company_name": serializers.CharField(),
        "title": serializers.CharField(),
        "description": serializers.CharField(),
        "salary_min": serializers.IntegerField(),
        "salary_max": serializers.IntegerField(),
        "salary_type": serializers.CharField(),
        "contact_channel": serializers.CharField(),
    })})
    def post(self, request, drop_id):
        company = get_employer_company(request.user)
        drop = (
            MicroTaskDrop.objects.filter(id=drop_id, task__company=company)
            .select_related("task", "candidate__candidate_profile")
            .first()
        )
        if not drop:
            raise FSPAPIError("not_found", "Not found", "Submission not found", 404)

        profile = getattr(drop.candidate, "candidate_profile", None)
        title = f"{drop.task.specialization.capitalize()} Developer ({drop.task.title})"
        description = f"Based on your solution to micro-task '{drop.task.title}'."

        salary_min = getattr(profile, "salary_min", None) or 200000
        salary_max = getattr(profile, "salary_max", None) or 300000
        salary_type = getattr(profile, "salary_type", "gross") or "gross"

        return Response(
            {
                "candidate_id": str(drop.candidate_id),
                "candidate_public_id": getattr(profile, "public_id", ""),
                "candidate_name": getattr(profile, "full_name", ""),
                "company_id": str(company.id),
                "company_name": company.name,
                "title": title,
                "description": description,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_type": salary_type,
                "contact_channel": "platform",
            }
        )


class PositionHealthView(views.APIView):
    """Need Health analytics for a position: funnel metrics, decline reasons, diagnosis (Task BE-20)."""

    permission_classes = [IsEmployer]

    @extend_schema(
        responses={
            200: inline_serializer(
                "PositionHealthResponse",
                fields={
                    "position_id": serializers.CharField(),
                    "title": serializers.CharField(),
                    "total_offers": serializers.IntegerField(),
                    "accepted_offers": serializers.IntegerField(),
                    "declined_offers": serializers.IntegerField(),
                    "expired_offers": serializers.IntegerField(),
                    "acceptance_rate": serializers.FloatField(),
                    "decline_rate": serializers.FloatField(),
                    "decline_reasons": serializers.DictField(),
                    "top_decline_reason": serializers.CharField(allow_null=True),
                    "health_status": serializers.CharField(),
                    "diagnosis": serializers.CharField(),
                    "credits_remaining": serializers.IntegerField(),
                    "weekly_credits_remaining": serializers.IntegerField(),
                },
            )
        }
    )
    def get(self, request, pk):
        company = get_employer_company(request.user)
        position = Position.objects.filter(id=pk, company=company).first()
        if not position:
            raise FSPAPIError("not_found", "Not found", "Position not found", 404)

        from core.enums import DeclineReason, OfferStatus
        from django.db.models import Count, Q
        from outreach.models import Offer

        from matching.antifraud import get_remaining_position_credits

        offers = Offer.objects.filter(position_id=position.id)
        counts = offers.aggregate(
            total=Count("id"),
            accepted=Count("id", filter=Q(status=OfferStatus.ACCEPTED)),
            declined=Count("id", filter=Q(status=OfferStatus.DECLINED)),
            expired=Count("id", filter=Q(status=OfferStatus.EXPIRED)),
        )
        total_offers = counts["total"]
        accepted_offers = counts["accepted"]
        declined_offers = counts["declined"]
        expired_offers = counts["expired"]

        acceptance_rate = round(accepted_offers / total_offers, 2) if total_offers > 0 else 0.0
        decline_rate = round(declined_offers / total_offers, 2) if total_offers > 0 else 0.0

        reason_counts = dict(
            offers.filter(status=OfferStatus.DECLINED)
            .values_list("decline_reason")
            .annotate(c=Count("id"))
        )
        decline_reasons = {
            choice[0]: reason_counts.get(choice[0], 0)
            for choice in DeclineReason.choices
        }

        declined_counts = {r: c for r, c in decline_reasons.items() if c > 0}
        top_decline_reason = (
            max(declined_counts, key=declined_counts.get) if declined_counts else None
        )

        if total_offers == 0:
            health_status = "good"
            diagnosis = "Нет отправленных офферов. Рекомендуется начать подбор кандидатов."
        elif decline_rate >= 0.6:
            health_status = "critical"
        elif decline_rate >= 0.4 or acceptance_rate < 0.2:
            health_status = "needs_attention"
        else:
            health_status = "good"

        if top_decline_reason == DeclineReason.SALARY:
            diagnosis = "Кандидаты чаще всего отклоняют оффер из-за зарплаты. Рекомендуется повысить вилку зарплаты."
        elif top_decline_reason == DeclineReason.FORMAT:
            diagnosis = "Кандидаты отклоняют оффер из-за формата работы (удаленка/офис). Рассмотрите возможность удаленной работы."
        elif top_decline_reason == DeclineReason.STACK:
            diagnosis = "Отказы связаны с несоответствием стека технологий. Рекомендуется пересмотреть ключевые требования."
        elif top_decline_reason == DeclineReason.COMPANY:
            diagnosis = "Отказы связаны с компанией или позиционированием. Улучшите описание проекта и условий."
        elif top_decline_reason == DeclineReason.TIMING:
            diagnosis = "Кандидаты не готовы менять работу прямо сейчас. Поддерживайте контакт для будущего найма."
        elif top_decline_reason == DeclineReason.NOT_LOOKING:
            diagnosis = "Кандидаты не ищут работу в данный момент."
        elif health_status in ["critical", "needs_attention"]:
            diagnosis = "Высокий процент отказов по офферам. Рекомендуется оптимизировать условия вакансии."
        else:
            diagnosis = "Позиция в хорошем состоянии, воронка найма сбалансирована."

        credits_remaining = get_remaining_position_credits(position)

        return Response(
            {
                "position_id": str(position.id),
                "title": position.title,
                "total_offers": total_offers,
                "accepted_offers": accepted_offers,
                "declined_offers": declined_offers,
                "expired_offers": expired_offers,
                "acceptance_rate": acceptance_rate,
                "decline_rate": decline_rate,
                "decline_reasons": decline_reasons,
                "top_decline_reason": top_decline_reason,
                "health_status": health_status,
                "diagnosis": diagnosis,
                "credits_remaining": credits_remaining,
                "weekly_credits_remaining": credits_remaining,
            }
        )



