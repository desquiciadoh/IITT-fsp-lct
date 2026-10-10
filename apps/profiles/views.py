"""Profiles app API views."""

import hashlib
import logging
import traceback

from core.enums import (
    ConsentType,
    DeclineReason,
    Grade,
    LeagueStatus,
    OfferStatus,
    Specialization,
    UserRole,
)
from core.errors import FSPAPIError, InvalidTransition, OfferExpired, VersionConflict
from django.db import transaction
from django.http import Http404, HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from identity.models import AuditLog, Consent
from outreach.models import Offer
from outreach.services import OfferService
from rest_framework import permissions, serializers, views
from rest_framework.response import Response

from profiles.models import CandidateProfile, Skill, generate_public_id
from profiles.pdf_service import generate_player_card_pdf
from profiles.serializers import (
    CandidateProfileSerializer,
    CandidateProfileUpdateSerializer,
    ConsentsResponseSerializer,
    ConsentUpdateSerializer,
    TaxonomySerializer,
)

logger = logging.getLogger(__name__)


class CandidateMeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CandidateProfileSerializer

    @extend_schema(responses={200: CandidateProfileSerializer})
    def get(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError(
                "forbidden", "Forbidden", "Only candidates have a candidate profile", 403
            )

        profile = CandidateProfile.objects.filter(user=request.user).first()
        if not profile:
            raise FSPAPIError("not_found", "Not found", "Candidate profile not found", 404)
        serializer = CandidateProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        request=CandidateProfileUpdateSerializer, responses={200: CandidateProfileSerializer}
    )
    def put(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError(
                "forbidden", "Forbidden", "Only candidates have a candidate profile", 403
            )

        profile, _ = CandidateProfile.objects.get_or_create(
            user=request.user, defaults={"public_id": generate_public_id()}
        )
        serializer = CandidateProfileUpdateSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed", "Validation failed", errors=serializer.errors, status_code=422
            )
        serializer.save()

        return Response(CandidateProfileSerializer(profile, context={"request": request}).data)


class ConsentsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: ConsentsResponseSerializer})
    def get(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError("forbidden", "Forbidden", "Only candidates manage consents", 403)

        consents = {}
        for ct in ConsentType.values:
            latest = request.user.consents.filter(type=ct).order_by("-created_at").first()
            consents[ct] = latest.granted if latest else False
        return Response(consents)

    @extend_schema(request=ConsentUpdateSerializer, responses={200: ConsentsResponseSerializer})
    @transaction.atomic
    def put(self, request):
        if request.user.role != UserRole.CANDIDATE:
            raise FSPAPIError("forbidden", "Forbidden", "Only candidates manage consents", 403)

        serializer = ConsentUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed", "Validation failed", errors=serializer.errors, status_code=422
            )

        data = serializer.validated_data
        version = data.get("version", "1.0")
        client_ip = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        for consent_type in [ConsentType.PROCESSING, ConsentType.PUBLICATION, ConsentType.FSP_SYNC]:
            if consent_type in data:
                granted = data[consent_type]
                Consent.objects.create(
                    user=request.user,
                    type=consent_type,
                    granted=granted,
                    version=version,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                AuditLog.objects.create(
                    actor=request.user,
                    action=f"consent_{'granted' if granted else 'revoked'}",
                    target_type="Consent",
                    target_id=consent_type,
                    meta={"version": version, "granted": granted},
                )

                # If publication consent revoked, withdraw pending offers (SENT, VIEWED)
                if consent_type == ConsentType.PUBLICATION and not granted:
                    pending_offers = Offer.objects.filter(
                        candidate=request.user,
                        status__in=[OfferStatus.SENT, OfferStatus.VIEWED],
                    )
                    for offer in pending_offers:
                        try:
                            OfferService.transition(
                                offer_id=offer.id,
                                new_status=OfferStatus.WITHDRAWN,
                                expected_version=offer.version,
                                actor_id=request.user.id,
                            )
                        except VersionConflict:
                            try:
                                fresh_offer = Offer.objects.filter(id=offer.id).first()
                                if fresh_offer and fresh_offer.can_transition_to(
                                    OfferStatus.WITHDRAWN
                                ):
                                    OfferService.transition(
                                        offer_id=fresh_offer.id,
                                        new_status=OfferStatus.WITHDRAWN,
                                        expected_version=fresh_offer.version,
                                        actor_id=request.user.id,
                                    )
                            except (InvalidTransition, OfferExpired, VersionConflict) as e:
                                logger.exception(
                                    "Failed to withdraw offer %s on publication revocation after retry: %s",
                                    offer.id,
                                    e,
                                )
                            except Exception as e:
                                logger.exception(
                                    "Unexpected error withdrawing offer %s on publication revocation after retry: %s",
                                    offer.id,
                                    e,
                                )
                        except (InvalidTransition, OfferExpired) as e:
                            logger.exception(
                                "Cannot withdraw offer %s on publication revocation: %s",
                                offer.id,
                                e,
                            )
                        except Exception as e:
                            logger.exception(
                                "Unexpected error withdrawing offer %s on publication revocation: %s",
                                offer.id,
                                e,
                            )

        # Return updated consents
        consents = {}
        for ct in ConsentType.values:
            latest = request.user.consents.filter(type=ct).order_by("-created_at").first()
            consents[ct] = latest.granted if latest else False

        return Response(consents)


class PlayerCardPdfView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={(200, "application/pdf"): bytes},
        description="Generate candidate player card PDF",
    )
    def get(self, request):
        profile = CandidateProfile.objects.filter(user=request.user).first()
        if not profile:
            raise Http404("Candidate profile not found")

        pdf_bytes = generate_player_card_pdf(profile)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="player_card_{profile.public_id}.pdf"'
        return response


class VerifyPublicIdView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "verify"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "specialization",
                str,
                OpenApiParameter.QUERY,
                description="Specialization filter",
                required=False,
            ),
        ],
        responses={
            200: inline_serializer(
                "VerifyPublicIdResponse",
                fields={
                    "public_id": serializers.CharField(),
                    "valid": serializers.BooleanField(),
                    "specialization": serializers.CharField(allow_null=True),
                    "grade": serializers.CharField(allow_null=True),
                    "status": serializers.CharField(allow_null=True),
                    "rating": serializers.IntegerField(allow_null=True),
                    "issued_at": serializers.DateTimeField(allow_null=True),
                },
            )
        },
    )
    def get(self, request, public_id):
        if not public_id or len(public_id) < 8:
            raise FSPAPIError("not_found", "Not found", "Invalid or unknown public ID format", 404)

        profile = CandidateProfile.objects.filter(public_id=public_id).first()
        if not profile:
            raise FSPAPIError(
                "not_found", "Not found", "Profile with this public_id not found", 404
            )

        # Respect publication consent
        latest_pub = (
            profile.user.consents.filter(type=ConsentType.PUBLICATION)
            .order_by("-created_at")
            .first()
        )
        if not latest_pub or not latest_pub.granted:
            return Response(
                {
                    "public_id": profile.public_id,
                    "valid": False,
                    "specialization": None,
                    "grade": None,
                    "status": None,
                    "rating": None,
                    "issued_at": None,
                }
            )

        spec = request.query_params.get("specialization")
        league_qs = profile.user.league_memberships.all()
        if spec:
            league_qs = league_qs.filter(specialization=spec)

        # Deterministic ordering
        league = (
            league_qs.filter(confirmed_at__isnull=False).order_by("-confirmed_at", "-id").first()
        )
        if not league:
            league = league_qs.order_by("-id").first()

        is_valid = bool(league and league.status == LeagueStatus.CONFIRMED and league.confirmed_at)
        return Response(
            {
                "public_id": profile.public_id,
                "valid": is_valid,
                "specialization": league.specialization if league else profile.specialization,
                "grade": league.grade if league else profile.claimed_grade,
                "status": league.status if league else "pending",
                "rating": league.rating if league else 1000,
                "issued_at": league.confirmed_at.isoformat()
                if (league and league.confirmed_at)
                else None,
            }
        )


class ResumeParseView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "resume"

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                    }
                },
                "required": ["file"],
            }
        },
        responses={
            200: inline_serializer(
                "ResumeParseResponse",
                fields={
                    "prefill": serializers.JSONField(),
                    "unknown_terms": serializers.ListField(child=serializers.CharField()),
                    "source": serializers.CharField(),
                },
            )
        },
    )
    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            raise FSPAPIError("validation_failed", "Validation failed", "Missing PDF file", 422)

        # B22: Enforce ≤5 MB size limit
        if file_obj.size > 5 * 1024 * 1024:
            raise FSPAPIError(
                "validation_failed", "File too large", "Resume file size must not exceed 5 MB", 422
            )

        # B22: MIME and filename check
        if not file_obj.name.lower().endswith(".pdf"):
            raise FSPAPIError(
                "unreadable_pdf", "Invalid file type", "Only PDF files are supported", 422
            )

        content_type = getattr(file_obj, "content_type", "") or ""
        if content_type and content_type.lower() not in (
            "application/pdf",
            "application/x-pdf",
            "application/octet-stream",
            "binary/octet-stream",
        ):
            raise FSPAPIError(
                "unreadable_pdf", "Invalid file type", "Only PDF files are supported", 422
            )

        file_bytes = file_obj.read()

        # Check PDF magic bytes (%PDF)
        if not file_bytes.startswith(b"%PDF"):
            raise FSPAPIError(
                "unreadable_pdf",
                "Invalid PDF header",
                "Файл PDF поврежден или не является корректным PDF-документом.",
                422,
            )

        try:
            from llm_gateway import FakeLlm, UnreadablePdf, parse_resume
        except ImportError:
            logger.error("llm_gateway package is not available")
            raise FSPAPIError(
                "resume_parse_failed",
                "Сервис распознавания недоступен",
                "Заполните профиль вручную или попробуйте позже.",
                503,
            )

        parse_res_data = None
        try:
            from profiles.tasks import parse_resume_task

            async_res = parse_resume_task.apply_async(args=[file_bytes], queue="llm")
            parse_res_data = async_res.get(timeout=15)
        except UnreadablePdf:
            logger.info("Resume rejected as unreadable (sha=%s)", hashlib.sha256(file_bytes).hexdigest()[:12])
            raise FSPAPIError(
                "unreadable_pdf",
                "Не удалось прочитать PDF",
                "Файл PDF поврежден, защищен паролем или не содержит распознаваемого текста.",
                422,
            )
        except Exception as celery_err:
            logger.warning(
                "Celery parse_resume failed or timed out (%s), falling back to rules",
                type(celery_err).__name__,
            )
            try:
                parse_res = parse_resume(file_bytes, gateway=FakeLlm())
                parse_res_data = {
                    "prefill": parse_res.prefill,
                    "unknown_terms": parse_res.unknown_terms,
                    "source": parse_res.source,
                }
            except UnreadablePdf:
                logger.info("Resume rejected as unreadable (sha=%s)", hashlib.sha256(file_bytes).hexdigest()[:12])
                raise FSPAPIError(
                    "unreadable_pdf",
                    "Не удалось прочитать PDF",
                    "Файл PDF поврежден, защищен паролем или не содержит распознаваемого текста.",
                    422,
                )
            except Exception as e:
                file_sha = hashlib.sha256(file_bytes).hexdigest()[:12]
                frames = " > ".join(
                    f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
                    for frame in traceback.extract_tb(e.__traceback__)
                )
                logger.error("Resume parse failed (%s, sha=%s) at %s", type(e).__name__, file_sha, frames)
                raise FSPAPIError(
                    "resume_parse_failed",
                    "Не удалось разобрать резюме",
                    "Заполните профиль вручную или попробуйте позже.",
                    500,
                ) from None

        return Response({
            "prefill": parse_res_data["prefill"],
            "unknown_terms": parse_res_data["unknown_terms"],
            "source": parse_res_data["source"],
        })


class TaxonomyView(views.APIView):
    """Platform taxonomy: specializations, grades, skills, and decline reasons (G3)."""

    permission_classes = [permissions.AllowAny]
    serializer_class = TaxonomySerializer

    @extend_schema(responses={200: TaxonomySerializer})
    def get(self, request):
        specializations = [
            {
                "id": Specialization.BACKEND,
                "name": "Backend",
                "topics": [
                    "sql.aggregation",
                    "complexity",
                    "algorithms",
                    "databases",
                    "concurrency",
                ],
            },
            {
                "id": Specialization.FRONTEND,
                "name": "Frontend",
                "topics": ["js.closure", "javascript", "react", "css_html", "performance"],
            },
            {
                "id": Specialization.ML_DATA,
                "name": "ML & Data",
                "topics": ["python", "ml_fundamentals", "data_engineering", "math_stats"],
            },
        ]

        grades = [
            {
                "id": Grade.INTERN,
                "name": "Intern",
                "descriptor": "Стажер / начальные базовые навыки",
                "rating_cut": 800,
            },
            {
                "id": Grade.JUNIOR,
                "name": "Junior",
                "descriptor": "Младший специалист / базовые практические навыки",
                "rating_cut": 960,
            },
            {
                "id": Grade.MIDDLE,
                "name": "Middle",
                "descriptor": "Специалист / самостоятельное решение задач и практический опыт",
                "rating_cut": 1120,
            },
            {
                "id": Grade.SENIOR,
                "name": "Senior",
                "descriptor": "Ведущий специалист / глубокая экспертиза и проектирование",
                "rating_cut": 1300,
            },
        ]

        skills_qs = Skill.objects.all()
        if skills_qs.exists():
            skills = [
                {
                    "id": s.id,
                    "name": s.name,
                    "aliases": s.aliases or [],
                    "topic": s.topic or "",
                }
                for s in skills_qs
            ]
        else:
            skills = [
                {"id": "python", "name": "Python", "aliases": ["py"], "topic": "backend"},
                {"id": "django", "name": "Django", "aliases": ["drf"], "topic": "backend"},
                {
                    "id": "postgresql",
                    "name": "PostgreSQL",
                    "aliases": ["postgres", "psql"],
                    "topic": "backend",
                },
                {"id": "docker", "name": "Docker", "aliases": ["container"], "topic": "backend"},
                {"id": "redis", "name": "Redis", "aliases": [], "topic": "backend"},
                {"id": "celery", "name": "Celery", "aliases": [], "topic": "backend"},
                {"id": "fastapi", "name": "FastAPI", "aliases": [], "topic": "backend"},
                {"id": "react", "name": "React", "aliases": ["react.js"], "topic": "frontend"},
                {"id": "typescript", "name": "TypeScript", "aliases": ["ts"], "topic": "frontend"},
                {"id": "javascript", "name": "JavaScript", "aliases": ["js"], "topic": "frontend"},
                {"id": "pytorch", "name": "PyTorch", "aliases": ["torch"], "topic": "ml_data"},
                {"id": "pandas", "name": "Pandas", "aliases": [], "topic": "ml_data"},
            ]

        decline_reasons = [{"id": choice[0], "name": choice[1]} for choice in DeclineReason.choices]

        data = {
            "specializations": specializations,
            "grades": grades,
            "skills": skills,
            "decline_reasons": decline_reasons,
        }
        return Response(data)
