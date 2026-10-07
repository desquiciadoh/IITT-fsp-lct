"""Identity app serializers and views."""
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from rest_framework import serializers, status, views, permissions
from rest_framework.response import Response
from django.conf import settings

from identity.models import User, Identity, Consent, AuditLog
from core.enums import UserRole, ConsentType, IdentityProvider
from core.errors import FSPAPIError


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'is_email_verified', 'is_demo', 'clock_offset_days', 'created_at']
        read_only_fields = ['id', 'is_email_verified', 'created_at']


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=UserRole.choices, default=UserRole.CANDIDATE)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already registered')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', UserRole.CANDIDATE)
        )
        # In demo mode, automatically verify email or provide verification link
        if settings.DEMO_MODE:
            user.email_verified_at = timezone.now()
            user.save(update_fields=['email_verified_at'])
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


from drf_spectacular.utils import extend_schema, inline_serializer

# --- Views ---

class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    @extend_schema(request=RegisterSerializer, responses={201: inline_serializer('RegisterResponse', fields={'user_id': serializers.UUIDField(), 'email': serializers.EmailField(), 'role': serializers.CharField(), 'email_verified': serializers.BooleanField()})})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        
        user = serializer.save()
        return Response({
            'user_id': str(user.id),
            'email': user.email,
            'role': user.role,
            'email_verified': user.is_email_verified,
        }, status=status.HTTP_201_CREATED)


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    @extend_schema(request=LoginSerializer, responses={200: inline_serializer('LoginResponse', fields={'id': serializers.UUIDField(), 'role': serializers.CharField(), 'email': serializers.EmailField(), 'email_verified': serializers.BooleanField(), 'demo': serializers.BooleanField(), 'company_id': serializers.UUIDField(allow_null=True)})})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        
        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']
        
        user = authenticate(request, email=email, password=password)
        if not user:
            raise FSPAPIError(
                code='bad_credentials',
                title='Invalid credentials',
                detail='Incorrect email or password.',
                status_code=401
            )
        
        login(request, user)
        
        company_id = None
        if user.role == UserRole.EMPLOYER:
            membership = user.company_memberships.first()
            if membership:
                company_id = str(membership.company_id)
        
        return Response({
            'id': str(user.id),
            'role': user.role,
            'email': user.email,
            'email_verified': user.is_email_verified,
            'demo': user.is_demo,
            'company_id': company_id,
        })


class LogoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={204: None})
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
        
        onboarding_step = 'done'
        if user.role == UserRole.CANDIDATE:
            if not user.consents.filter(type=ConsentType.PROCESSING, granted=True).exists():
                onboarding_step = 'consent'
            elif not hasattr(user, 'candidate_profile') or not user.candidate_profile.specialization:
                onboarding_step = 'profile'
            elif not user.league_memberships.filter(status__in=['confirmed', 'unconfirmed']).exists():
                onboarding_step = 'qualification'
        
        return Response({
            'id': str(user.id),
            'role': user.role,
            'email': user.email,
            'email_verified': user.is_email_verified,
            'demo': user.is_demo,
            'company_id': company_id,
            'onboarding_step': onboarding_step,
        })


class DemoPersonaView(views.APIView):
    """Switch or login as demo personas: candidate_fsp, candidate_plain, employer."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=inline_serializer('PersonaRequest', fields={'persona': serializers.CharField(default='candidate_fsp')}),
        responses={200: MeResponseSerializer}
    )
    def post(self, request):
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                code='forbidden',
                title='Demo mode disabled',
                detail='Persona login is only available in DEMO_MODE',
                status_code=403
            )
        
        persona = request.data.get('persona', 'candidate_fsp')
        email_map = {
            'candidate_fsp': 'anna.fsp@example.com',
            'candidate_plain': 'alex.dev@example.com',
            'employer': 'techlead@yandex-mock.ru'
        }
        
        email = email_map.get(persona, f'{persona}@example.com')
        user = User.objects.filter(email=email).first()
        if not user:
            role = UserRole.EMPLOYER if persona == 'employer' else UserRole.CANDIDATE
            user = User.objects.create_user(
                email=email,
                password='demopassword',
                role=role,
                is_demo=True,
                email_verified_at=timezone.now()
            )
        
        login(request, user)
        company_id = None
        if user.role == UserRole.EMPLOYER:
            membership = user.company_memberships.first()
            if membership:
                company_id = str(membership.company_id)
                
        return Response({
            'id': str(user.id),
            'role': user.role,
            'email': user.email,
            'email_verified': user.is_email_verified,
            'demo': True,
            'company_id': company_id,
        })


class DemoTimeTravelView(views.APIView):
    """Time-travel endpoint for jury/demo testing cooldowns."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=inline_serializer('TimeTravelRequest', fields={'days': serializers.IntegerField(default=30)}),
        responses={200: inline_serializer('TimeTravelResponse', fields={'clock_offset_days': serializers.IntegerField()})}
    )
    def post(self, request):
        if not settings.DEMO_MODE:
            raise FSPAPIError(
                code='forbidden',
                title='Demo mode disabled',
                detail='Time travel is only available in DEMO_MODE',
                status_code=403
            )
        
        days = int(request.data.get('days', 30))
        if request.user.is_authenticated:
            request.user.clock_offset_days += days
            request.user.save(update_fields=['clock_offset_days'])
            return Response({'clock_offset_days': request.user.clock_offset_days})
        
        return Response({'clock_offset_days': days})
