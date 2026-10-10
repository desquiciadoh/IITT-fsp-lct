"""Identity app serializers and views."""

import secrets

from core.enums import ConsentType, IdentityProvider, UserRole
from core.errors import FSPAPIError, FSPIdAlreadyLinked
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from fsp_sync.models import FSPLink
from fsp_sync.services import link_fsp_id
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response

from identity.models import Identity, User
from identity.oidc import (
    build_authorization_url,
    exchange_code_for_tokens,
    verify_and_decode_id_token,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "role",
            "is_email_verified",
            "is_demo",
            "clock_offset_days",
            "created_at",
        ]
        read_only_fields = ["id", "is_email_verified", "created_at"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(
        choices=[(UserRole.CANDIDATE, "Candidate"), (UserRole.EMPLOYER, "Employer")],
        default=UserRole.CANDIDATE,
    )

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=validated_data.get("role", UserRole.CANDIDATE),
        )
        # In demo mode, automatically verify email or provide verification link
        if settings.DEMO_MODE:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])

        if user.role == UserRole.CANDIDATE:
            from profiles.models import CandidateProfile, generate_public_id

            CandidateProfile.objects.create(
                user=user,
                public_id=generate_public_id(),
            )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class MeResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.CharField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()
    demo = serializers.BooleanField()
    company_id = serializers.UUIDField(required=False, allow_null=True)
    onboarding_step = serializers.CharField(required=False)


# --- Views ---


class CsrfView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(responses={204: None})
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_scope = "register"

    @extend_schema(
        request=RegisterSerializer,
        responses={
            201: inline_serializer(
                "RegisterResponse",
                fields={
                    "user_id": serializers.UUIDField(),
                    "email": serializers.EmailField(),
                    "role": serializers.CharField(),
                    "email_verified": serializers.BooleanField(),
                    "verify_link": serializers.CharField(required=False),
                },
            )
        },
    )
    @method_decorator(csrf_protect)
    def post(self, request):
        role_input = request.data.get("role")
        if role_input in (UserRole.ADMIN, "admin"):
            raise FSPAPIError(
                code="invalid_role",
                title="Invalid role",
                detail="Admin role cannot be registered.",
                status_code=400,
            )

        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)

        user = serializer.save()
        resp_data = {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "email_verified": user.is_email_verified,
        }
        if settings.DEMO_MODE:
            token = signing.dumps({"user_id": str(user.id)}, salt="email-verify")
            resp_data["verify_link"] = f"/verify-email?token={token}"
        return Response(resp_data, status=status.HTTP_201_CREATED)


class VerifyEmailRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class VerifyEmailView(views.APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VerifyEmailRequestSerializer

    @extend_schema(request=VerifyEmailRequestSerializer, responses={204: None})
    def post(self, request):
        serializer = VerifyEmailRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                errors=serializer.errors,
                status_code=422,
            )

        token = serializer.validated_data["token"]
        try:
            data = signing.loads(token, salt="email-verify", max_age=86400 * 3)
            user_id = data.get("user_id")
            user = User.objects.get(id=user_id)
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (signing.BadSignature, User.DoesNotExist):
            raise FSPAPIError(
                "invalid_token",
                "Invalid token",
                "Invalid or expired verification token",
                400,
            )


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: inline_serializer(
                "LoginResponse",
                fields={
                    "id": serializers.UUIDField(),
                    "role": serializers.CharField(),
                    "email": serializers.EmailField(),
                    "email_verified": serializers.BooleanField(),
                    "demo": serializers.BooleanField(),
                    "company_id": serializers.UUIDField(allow_null=True),
                },
            )
        },
    )
    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)

        email = serializer.validated_data["email"].lower()
        password = serializer.validated_data["password"]

        user = authenticate(request, email=email, password=password)
        if not user:
            raise FSPAPIError(
                code="bad_credentials",
                title="Invalid credentials",
                detail="Incorrect email or password.",
                status_code=401,
            )

        login(request, user)

        company_id = None
        if user.role == UserRole.EMPLOYER:
            membership = user.company_memberships.first()
            if membership:
                company_id = str(membership.company_id)

        return Response(
            {
                "id": str(user.id),
                "role": user.role,
                "email": user.email,
                "email_verified": user.is_email_verified,
                "demo": user.is_demo,
                "company_id": company_id,
            }
        )


class LogoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeResponseSerializer

    @extend_schema(responses={200: MeResponseSerializer})
    def get(self, request):
        user = request.user
        company_id = None
        if user.role == UserRole.EMPLOYER:
            membership = user.company_memberships.first()
            if membership:
                company_id = str(membership.company_id)

        onboarding_step = "done"
        if user.role == UserRole.CANDIDATE:
            if not user.consents.filter(type=ConsentType.PROCESSING, granted=True).exists():
                onboarding_step = "consent"
            elif (
                not hasattr(user, "candidate_profile") or not user.candidate_profile.specialization
            ):
                onboarding_step = "profile"
            elif not user.league_memberships.filter(
                status__in=["confirmed", "unconfirmed"]
            ).exists():
                onboarding_step = "qualification"

        return Response(
            {
                "id": str(user.id),
                "role": user.role,
                "email": user.email,
                "email_verified": user.is_email_verified,
                "demo": user.is_demo,
                "company_id": company_id,
                "onboarding_step": onboarding_step,
            }
        )


class DemoPersonaView(views.APIView):
    """Switch or login as demo personas: candidate_fsp, candidate_plain, employer."""

    permission_classes = [permissions.AllowAny]

    PERSONA_MAP = {
        "candidate_fsp": "anna.fsp@example.com",
        "candidate_plain": "alex.dev@example.com",
        "employer": "techlead@yandex-mock.ru",
    }

    @extend_schema(
        request=inline_serializer(
            "PersonaRequest",
            fields={
                "persona": serializers.ChoiceField(
                    choices=["candidate_fsp", "candidate_plain", "employer"]
                ),
            },
        ),
        responses={200: MeResponseSerializer},
    )
    @method_decorator(csrf_protect)
    def post(self, request):
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                code="forbidden",
                title="Demo mode disabled",
                detail="Persona login is only available in DEMO_MODE",
                status_code=403,
            )

        if request.user.is_authenticated and not getattr(request.user, "is_demo", False):
            raise FSPAPIError(
                code="forbidden",
                title="Forbidden",
                detail="Persona switching is only available for demo users",
                status_code=403,
            )

        persona = request.data.get("persona", "")
        if persona not in self.PERSONA_MAP:
            raise FSPAPIError(
                code="validation_failed",
                title="Invalid persona",
                detail=f"persona must be one of: {', '.join(self.PERSONA_MAP)}",
                status_code=422,
            )

        email = self.PERSONA_MAP[persona]
        user = User.objects.filter(email=email, is_demo=True).first()
        if not user:
            raise FSPAPIError(
                code="not_found",
                title="Persona not found",
                detail="Demo persona has not been seeded. Run manage.py seed first.",
                status_code=404,
            )

        login(request, user)
        company_id = None
        if user.role == UserRole.EMPLOYER:
            membership = user.company_memberships.first()
            if membership:
                company_id = str(membership.company_id)

        return Response(
            {
                "id": str(user.id),
                "role": user.role,
                "email": user.email,
                "email_verified": user.is_email_verified,
                "demo": True,
                "company_id": company_id,
            }
        )


class DemoTimeTravelView(views.APIView):
    """Time-travel endpoint for jury/demo testing cooldowns."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            "TimeTravelRequest",
            fields={"days": serializers.IntegerField(min_value=0, max_value=365)},
        ),
        responses={
            200: inline_serializer(
                "TimeTravelResponse", fields={"clock_offset_days": serializers.IntegerField()}
            )
        },
    )
    def post(self, request):
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                code="forbidden",
                title="Demo mode disabled",
                detail="Time travel is only available in DEMO_MODE",
                status_code=403,
            )
        if not request.user.is_demo:
            raise FSPAPIError(
                code="forbidden",
                title="Forbidden",
                detail="Time travel is only available for demo users",
                status_code=403,
            )

        raw_days = request.data.get("days")
        if raw_days is None:
            raise FSPAPIError("validation_failed", "Missing days", "days is required", 422)
        try:
            days = int(raw_days)
        except (ValueError, TypeError):
            raise FSPAPIError("validation_failed", "Invalid days", "days must be an integer", 422)
        if days < 0 or days > 365:
            raise FSPAPIError(
                "validation_failed", "Invalid days", "days must be between 0 and 365", 422
            )

        request.user.clock_offset_days = days
        request.user.save(update_fields=["clock_offset_days"])
        return Response({"clock_offset_days": request.user.clock_offset_days})


class DemoResetView(views.APIView):
    """Resets the caller's persona data and clock offset in DEMO_MODE."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "DemoResetResponse",
                fields={
                    "status": serializers.CharField(),
                    "clock_offset_days": serializers.IntegerField(),
                },
            )
        },
    )
    def post(self, request):
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                code="forbidden",
                title="Demo mode disabled",
                detail="Demo reset is only available in DEMO_MODE",
                status_code=403,
            )
        if not request.user.is_demo:
            raise FSPAPIError(
                code="forbidden",
                title="Forbidden",
                detail="Demo reset is only available for demo users",
                status_code=403,
            )

        from core.demo_data import reset_demo_persona

        reset_demo_persona(request.user)

        return Response(
            {
                "status": "ok",
                "clock_offset_days": 0,
            }
        )


class FspIdLoginView(views.APIView):
    """Initiate OIDC flow for FSP ID login or linking (G15)."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("intent", str, description="Intent: login or link", default="login"),
        ],
        responses={302: None},
        description="Initiate OIDC flow for FSP ID login or linking",
    )
    def get(self, request):
        intent = request.query_params.get("intent", "login")
        if intent not in ["login", "link"]:
            raise FSPAPIError(
                "validation_failed",
                "Validation failed",
                "intent must be login or link",
                status_code=422,
            )

        if intent == "link":
            if not request.user.is_authenticated:
                raise FSPAPIError(
                    "unauthorized",
                    "Unauthorized",
                    "Authentication required to link FSP ID",
                    status_code=401,
                )
            if request.user.role != UserRole.CANDIDATE:
                raise FSPAPIError(
                    "forbidden",
                    "Forbidden",
                    "Only candidates can link FSP ID",
                    status_code=403,
                )

        auth_url, state = build_authorization_url(request, intent)
        return HttpResponseRedirect(auth_url)


class FspIdCallbackView(views.APIView):
    """OIDC callback endpoint for FSP ID login or linking (G15)."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("code", str, description="Authorization code", required=True),
            OpenApiParameter("state", str, description="State parameter", required=True),
        ],
        responses={
            302: None,
            409: OpenApiResponse(description="FSP ID already linked to another account"),
        },
        description="OIDC callback endpoint for FSP ID flow",
    )
    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            raise FSPAPIError(
                "validation_failed", "Validation failed", "code and state are required", 400
            )

        # One-shot: pop the flow state so a callback URL can't be replayed
        expected_state = request.session.pop("oidc_state", None)
        intent = request.session.pop("oidc_intent", "login")
        code_verifier = request.session.pop("oidc_verifier", "")
        redirect_uri = request.session.pop("oidc_redirect_uri", "")
        nonce = request.session.pop("oidc_nonce", None)
        if not expected_state or not secrets.compare_digest(state, expected_state):
            raise FSPAPIError("invalid_state", "Invalid state", "OIDC state mismatch", 400)

        token_response = exchange_code_for_tokens(code, code_verifier, redirect_uri)
        id_token = token_response.get("id_token")
        if not id_token:
            raise FSPAPIError(
                "token_exchange_failed",
                "Token exchange failed",
                "No id_token in token response",
                400,
            )

        claims = verify_and_decode_id_token(id_token, nonce=nonce)
        # Identity is keyed on the IdP's immutable `sub`; the participant ID is data.
        subject = claims.get("sub")
        participant_id = claims.get("fsp_participant_id") or subject
        for value in (subject, participant_id):
            if not value or not isinstance(value, str) or len(value) > 50:
                raise FSPAPIError(
                    "invalid_claims",
                    "Invalid claims",
                    "Missing or invalid sub / participant ID",
                    400,
                )

        if intent == "link":
            if not request.user.is_authenticated:
                raise FSPAPIError("unauthorized", "Unauthorized", "Authentication required", 401)

            # Invariant: Each participant_id maps to exactly one candidate
            existing_identity = (
                Identity.objects.filter(
                    provider=IdentityProvider.FSP_ID,
                    subject=subject,
                )
                .exclude(user=request.user)
                .first()
            )
            if existing_identity:
                raise FSPIdAlreadyLinked()

            existing_link = (
                FSPLink.objects.filter(
                    participant_id=participant_id,
                )
                .exclude(candidate=request.user)
                .first()
            )
            if existing_link:
                raise FSPIdAlreadyLinked()

            try:
                with transaction.atomic():
                    Identity.objects.update_or_create(
                        user=request.user,
                        provider=IdentityProvider.FSP_ID,
                        defaults={"subject": subject},
                    )
                    link_fsp_id(request.user, participant_id)
            except IntegrityError:
                raise FSPIdAlreadyLinked()

            return HttpResponseRedirect("/candidate/profile?fsp_linked=true")

        else:  # intent == 'login'
            identity = (
                Identity.objects.filter(
                    provider=IdentityProvider.FSP_ID,
                    subject=subject,
                )
                .select_related("user")
                .first()
            )

            if identity:
                user = identity.user
            else:
                email = (
                    claims.get("email")
                    or f"{participant_id.lower().replace('-', '')}@fsp-sports.ru"
                )
                # Never attach an FSP identity to an existing account by email:
                # the owner must log in and use intent=link instead.
                if User.objects.filter(email__iexact=email).exists():
                    raise FSPAPIError(
                        "account_exists",
                        "Account exists",
                        "An account with this email exists. Log in and link FSP ID from your profile.",
                        409,
                    )
                from profiles.models import CandidateProfile, generate_public_id

                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            email=email,
                            password=None,
                            role=UserRole.CANDIDATE,
                            email_verified_at=timezone.now()
                            if claims.get("email_verified") is True
                            else None,
                        )
                        CandidateProfile.objects.create(
                            user=user,
                            public_id=generate_public_id(),
                            full_name=claims.get("name") or f"Спортсмен {participant_id}",
                        )
                        Identity.objects.create(
                            user=user,
                            provider=IdentityProvider.FSP_ID,
                            subject=subject,
                        )
                        link_fsp_id(user, participant_id)
                except IntegrityError:
                    raise FSPIdAlreadyLinked()

            login(request, user)
            return HttpResponseRedirect("/?login=success")
