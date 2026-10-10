"""Assessment views."""

import json
import logging
from pathlib import Path

from core.enums import (
    AssessmentStatus,
    Grade,
    LeagueStatus,
    Specialization,
)
from core.errors import FSPAPIError
from core.pagination import FSPPagination
from core.permissions import IsCandidate
from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response

from assessment.models import AssessmentSession, LeagueMembership
from assessment.serializers import (
    AnswerRequestSerializer,
    AssessmentResultSerializer,
    AssessmentSessionSerializer,
    FallbackRequestSerializer,
    ItemViewSerializer,
    LeagueShelfSerializer,
    StartAssessmentSerializer,
    ValidationReportSerializer,
)
from assessment.services import AssessmentService, get_current_time_for_user

logger = logging.getLogger(__name__)


class EligibilityView(views.APIView):
    permission_classes = [IsCandidate]

    @extend_schema(
        responses={
            200: inline_serializer(
                "EligibilityResponse",
                fields={
                    "can_start": serializers.BooleanField(),
                    "next_attempt_at": serializers.CharField(required=False),
                    "promotion_available": serializers.BooleanField(),
                    "reason": serializers.CharField(required=False),
                    "active_session_id": serializers.CharField(required=False, allow_null=True),
                },
            )
        }
    )
    def get(self, request):
        spec = request.query_params.get("specialization", Specialization.BACKEND)
        user = request.user
        now = get_current_time_for_user(user)

        membership = LeagueMembership.objects.filter(candidate=user, specialization=spec).first()
        if membership and membership.next_attempt_at and membership.next_attempt_at > now:
            return Response(
                {
                    "can_start": False,
                    "next_attempt_at": membership.next_attempt_at.isoformat(),
                    "promotion_available": False,
                    "reason": "cooldown_active",
                }
            )

        # Check if active session already exists for this specialization
        active_session = AssessmentSession.objects.filter(
            candidate=user,
            specialization=spec,
            status=AssessmentStatus.IN_PROGRESS,
        ).first()

        return Response(
            {
                "can_start": active_session is None,
                "active_session_id": str(active_session.id) if active_session else None,
                "promotion_available": False,
            }
        )


class AssessmentListCreateView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AssessmentSessionSerializer

    @extend_schema(
        operation_id="assessments_list",
        responses={
            200: inline_serializer(
                "AssessmentPaginatedResponse",
                fields={
                    "items": AssessmentResultSerializer(many=True),
                    "total": serializers.IntegerField(),
                    "page": serializers.IntegerField(),
                    "pages": serializers.IntegerField(),
                },
            )
        },
    )
    def get(self, request):
        sessions = AssessmentSession.objects.filter(candidate=request.user).order_by("-started_at")
        paginator = FSPPagination()
        page = paginator.paginate_queryset(sessions, request, view=self)
        if page is not None:
            serializer = AssessmentResultSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = AssessmentResultSerializer(sessions, many=True)
        return Response(
            {
                "items": serializer.data,
                "total": len(serializer.data),
                "page": 1,
                "pages": 1,
            }
        )

    @extend_schema(request=StartAssessmentSerializer, responses={201: AssessmentSessionSerializer})
    def post(self, request):
        serializer = StartAssessmentSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        data = serializer.validated_data
        session = AssessmentService.start_assessment(
            user=request.user,
            specialization=data["specialization"],
            claimed_grade=data["claimed_grade"],
            mode=data.get("mode", "full"),
        )
        serializer = AssessmentSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AssessmentDetailView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AssessmentSessionSerializer

    @extend_schema(responses={200: AssessmentSessionSerializer})
    def get(self, request, pk):
        session = AssessmentSession.objects.filter(id=pk, candidate=request.user).first()
        if not session:
            raise FSPAPIError("not_found", "Not found", "Assessment session not found", 404)

        serializer = AssessmentSessionSerializer(session)
        return Response(serializer.data)


class AssessmentAnswerView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AnswerRequestSerializer

    @extend_schema(
        request=AnswerRequestSerializer,
        responses={
            200: inline_serializer(
                "AnswerResponse",
                fields={
                    "done": serializers.BooleanField(),
                    "next": ItemViewSerializer(required=False),
                    "result": AssessmentResultSerializer(required=False),
                },
            )
        },
    )
    def post(self, request, pk):
        serializer = AnswerRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        item_id = serializer.validated_data["item_id"]
        chosen_opt = serializer.validated_data.get("option_id")
        user_val = serializer.validated_data.get("value")
        answer_val = chosen_opt or user_val

        session, next_item, is_done = AssessmentService.submit_answer(
            user=request.user,
            session_id=pk,
            item_id=item_id,
            answer_val=answer_val,
            integrity=serializer.validated_data.get("integrity", {}),
        )

        if not is_done:
            return Response(
                {
                    "done": False,
                    "next": ItemViewSerializer(next_item).data,
                }
            )

        return Response(
            {
                "done": True,
                "result": AssessmentResultSerializer(session).data,
            }
        )


class AssessmentFinishView(views.APIView):
    """Abandon / finish early an in-progress assessment."""

    permission_classes = [IsCandidate]
    serializer_class = AssessmentResultSerializer

    @extend_schema(request=None, responses={200: AssessmentResultSerializer})
    def post(self, request, pk):
        session = AssessmentService.abandon_assessment(
            user=request.user,
            session_id=pk,
        )
        return Response(AssessmentResultSerializer(session).data)


class AssessmentResultView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AssessmentResultSerializer

    @extend_schema(responses={200: AssessmentResultSerializer})
    def get(self, request, pk):
        session = AssessmentSession.objects.filter(id=pk, candidate=request.user).first()
        if not session or session.status != AssessmentStatus.FINISHED:
            raise FSPAPIError("not_finished", "Not finished", "Assessment is not finished yet", 400)

        return Response(AssessmentResultSerializer(session).data)


class AssessmentFallbackView(views.APIView):
    """Fallback to a lower grade or short-test after an unconfirmed assessment (G5)."""

    permission_classes = [IsCandidate]
    serializer_class = FallbackRequestSerializer

    @extend_schema(
        request=FallbackRequestSerializer,
        responses={
            200: AssessmentResultSerializer,
            201: AssessmentSessionSerializer,
        },
    )
    def post(self, request, pk):
        serializer = FallbackRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed", "Validation failed", errors=serializer.errors, status_code=422
            )

        mode = serializer.validated_data.get("mode", "instant")
        session, is_new = AssessmentService.fallback(
            user=request.user,
            session_id=pk,
            mode=mode,
        )
        if is_new:
            return Response(
                AssessmentSessionSerializer(session).data, status=status.HTTP_201_CREATED
            )
        return Response(AssessmentResultSerializer(session).data, status=status.HTTP_200_OK)


class LeagueShelfView(views.APIView):
    """League shelves with candidate counts and median salary expectation (G7)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LeagueShelfSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="specialization",
                description="Specialization to filter by",
                required=False,
                type=str,
            ),
        ],
        responses={200: LeagueShelfSerializer(many=True)},
    )
    def get(self, request):
        import statistics

        from profiles.models import CandidateProfile

        spec_param = request.query_params.get("specialization")
        if spec_param:
            specs = [spec_param]
        else:
            specs = [s.value for s in Specialization]

        shelves = []
        for spec in specs:
            for grade in [Grade.INTERN, Grade.JUNIOR, Grade.MIDDLE, Grade.SENIOR]:
                memberships = LeagueMembership.objects.filter(
                    specialization=spec,
                    grade=grade,
                )
                confirmed = memberships.filter(status=LeagueStatus.CONFIRMED).count()
                unconfirmed = memberships.filter(status=LeagueStatus.UNCONFIRMED).count()

                candidate_ids = memberships.values_list("candidate_id", flat=True)
                salaries = list(
                    CandidateProfile.objects.filter(
                        user_id__in=candidate_ids,
                        salary_min__isnull=False,
                    ).values_list("salary_min", flat=True)
                )
                median_exp = int(round(statistics.median(salaries))) if salaries else None

                shelves.append(
                    {
                        "specialization": spec,
                        "grade": grade,
                        "confirmed": confirmed,
                        "unconfirmed": unconfirmed,
                        "median_expectation": median_exp,
                    }
                )

        return Response(shelves)


class LabReportView(views.APIView):
    """Validation Lab metrics report (G11).

    Serves validation/out/report.json if present; otherwise serves
    report.fixture.json labeled with synthetic_fixture=True.
    A corrupt report gives a logged 500 report_unreadable.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = ValidationReportSerializer

    @extend_schema(responses={200: ValidationReportSerializer})
    def get(self, request):
        report_file = Path(settings.BASE_DIR) / "validation" / "out" / "report.json"
        fixture_file = Path(settings.BASE_DIR) / "validation" / "out" / "report.fixture.json"

        if report_file.is_file():
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Response(data)
            except Exception as e:
                logger.exception("Corrupt report.json: %s", e)
                raise FSPAPIError(
                    "report_unreadable",
                    "Report unreadable",
                    "The validation report file is corrupt or unreadable.",
                    status_code=500,
                )

        if fixture_file.is_file():
            try:
                with open(fixture_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Response(data)
            except Exception as e:
                logger.exception("Corrupt report.fixture.json: %s", e)
                raise FSPAPIError(
                    "report_unreadable",
                    "Report unreadable",
                    "The validation report fixture file is corrupt or unreadable.",
                    status_code=500,
                )

        logger.error(
            "No validation report or fixture file found at %s or %s", report_file, fixture_file
        )
        raise FSPAPIError(
            "report_unreadable",
            "Report unreadable",
            "No validation report or fixture available.",
            status_code=500,
        )
