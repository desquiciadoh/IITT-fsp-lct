"""Assessment views."""
import hmac
import hashlib
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.response import Response

from assessment.models import AssessmentSession, AssessmentItem, ItemFamily, LeagueMembership
from assessment.serializers import (
    AssessmentSessionSerializer,
    AssessmentResultSerializer,
    AnswerRequestSerializer,
    ItemViewSerializer,
)
from assessment.engine import FAMILIES_REGISTRY, score_assessment
from core.enums import (
    AssessmentStatus,
    Grade,
    GradeDecision,
    LeagueStatus,
    Specialization,
    UserRole,
)
from core.errors import CooldownActive, AssessmentInProgress, ItemNotCurrent, FSPAPIError
from core.permissions import IsCandidate


def get_current_time_for_user(user) -> timezone.datetime:
    """Return current time adjusted for user's clock offset in DEMO_MODE."""
    now = timezone.now()
    if settings.DEMO_MODE and getattr(user, 'clock_offset_days', 0):
        now += timedelta(days=user.clock_offset_days)
    return now


from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

class EligibilityView(views.APIView):
    permission_classes = [IsCandidate]

    @extend_schema(responses={200: inline_serializer('EligibilityResponse', fields={
        'can_start': serializers.BooleanField(),
        'next_attempt_at': serializers.CharField(required=False),
        'promotion_available': serializers.BooleanField(),
        'reason': serializers.CharField(required=False),
        'active_session_id': serializers.CharField(required=False, allow_null=True),
    })})
    def get(self, request):
        spec = request.query_params.get('specialization', Specialization.BACKEND)
        user = request.user
        now = get_current_time_for_user(user)

        membership = LeagueMembership.objects.filter(candidate=user, specialization=spec).first()
        if membership and membership.next_attempt_at and membership.next_attempt_at > now:
            return Response({
                'can_start': False,
                'next_attempt_at': membership.next_attempt_at.isoformat(),
                'promotion_available': False,
                'reason': 'cooldown_active'
            })

        # Check if active session already exists
        active_session = AssessmentSession.objects.filter(
            candidate=user,
            status=AssessmentStatus.IN_PROGRESS
        ).first()

        return Response({
            'can_start': active_session is None,
            'active_session_id': str(active_session.id) if active_session else None,
            'promotion_available': False,
        })


class AssessmentListCreateView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AssessmentSessionSerializer

    @extend_schema(responses={200: AssessmentResultSerializer(many=True)})
    def get(self, request):
        sessions = AssessmentSession.objects.filter(candidate=request.user).order_by('-started_at')
        serializer = AssessmentResultSerializer(sessions, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=inline_serializer('StartAssessmentRequest', fields={
            'specialization': serializers.CharField(default='backend'),
            'claimed_grade': serializers.CharField(default='middle'),
            'mode': serializers.CharField(default='full'),
        }),
        responses={201: AssessmentSessionSerializer}
    )
    def post(self, request):
        user = request.user
        now = get_current_time_for_user(user)
        spec = request.data.get('specialization', Specialization.BACKEND)
        claimed_grade = request.data.get('claimed_grade', Grade.MIDDLE)
        mode = request.data.get('mode', 'full')

        # Check cooldown
        membership = LeagueMembership.objects.filter(candidate=user, specialization=spec).first()
        if membership and membership.next_attempt_at and membership.next_attempt_at > now:
            raise CooldownActive(membership.next_attempt_at.isoformat())

        # Check active session
        active = AssessmentSession.objects.filter(candidate=user, status=AssessmentStatus.IN_PROGRESS).first()
        if active:
            raise AssessmentInProgress()

        # Create session
        session = AssessmentSession.objects.create(
            candidate=user,
            specialization=spec,
            claimed_grade=claimed_grade,
            mode=mode,
            status=AssessmentStatus.IN_PROGRESS,
        )

        # Select families matching spec or shared
        families = [
            f for f in FAMILIES_REGISTRY.values()
            if f.spec == spec or f.spec == 'backend'  # fallback
        ]
        if not families:
            families = list(FAMILIES_REGISTRY.values())

        # Seed items
        for seq, family in enumerate(families[:3], start=1):
            seed_raw = f"{settings.ITEM_SEED_SECRET}:{session.id}:{family.family_id}:{seq}"
            seed = hashlib.sha256(seed_raw.encode()).hexdigest()
            instance = family.generate(seed)

            # Ensure ItemFamily DB row exists
            item_family_obj, _ = ItemFamily.objects.get_or_create(
                id=family.family_id,
                defaults={
                    'specs': [spec],
                    'topic': family.topic,
                    'format': 'choice',
                    'a': family.discrimination_a,
                    'b': family.difficulty_b,
                    'c': family.guessing_c,
                    'time_limit_s': family.time_limit_s,
                }
            )

            deadline = now + timedelta(seconds=instance.time_limit_s)
            AssessmentItem.objects.create(
                assessment=session,
                seq=seq,
                family=item_family_obj,
                seed=seed,
                view={
                    'stem_md': instance.stem_md,
                    'code': instance.code,
                    'options': instance.options,
                    'input_type': instance.input_type,
                    'time_limit_s': instance.time_limit_s,
                },
                key=instance.key,  # STRICTLY SERVER-SIDE!
                fingerprint=instance.fingerprint,
                deadline_at=deadline,
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
            raise FSPAPIError('not_found', 'Not found', 'Assessment session not found', 404)
        
        serializer = AssessmentSessionSerializer(session)
        return Response(serializer.data)


class AssessmentAnswerView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AnswerRequestSerializer

    @extend_schema(
        request=AnswerRequestSerializer,
        responses={200: inline_serializer('AnswerResponse', fields={
            'done': serializers.BooleanField(),
            'next': ItemViewSerializer(required=False),
            'result': AssessmentResultSerializer(required=False),
        })}
    )
    def post(self, request, pk):
        session = AssessmentSession.objects.filter(id=pk, candidate=request.user).first()
        if not session:
            raise FSPAPIError('not_found', 'Not found', 'Assessment session not found', 404)

        if session.status != AssessmentStatus.IN_PROGRESS:
            raise FSPAPIError('assessment_expired', 'Assessment closed', 'Assessment is no longer in progress', 400)

        serializer = AnswerRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise FSPAPIError('validation_failed', 'Validation failed', errors=serializer.errors, status_code=422)

        item_id = serializer.validated_data['item_id']
        chosen_opt = serializer.validated_data.get('option_id')
        user_val = serializer.validated_data.get('value')
        answer_val = chosen_opt or user_val

        current_item = session.items.filter(answered_at__isnull=True).order_by('seq').first()
        if not current_item or str(current_item.id) != str(item_id):
            raise ItemNotCurrent()

        now = get_current_time_for_user(request.user)

        # Server-side evaluation against key
        correct = (answer_val == current_item.key)

        current_item.answer = {'value': answer_val}
        current_item.correct = correct
        current_item.answered_at = now
        current_item.integrity = serializer.validated_data.get('integrity', {})
        current_item.save()

        # Check if more items exist
        next_item = session.items.filter(answered_at__isnull=True).order_by('seq').first()
        if next_item:
            return Response({
                'done': False,
                'next': ItemViewSerializer(next_item).data
            })

        # All items answered: compute IRT score and finalize
        items_data = [
            {'correct': it.correct, 'b': it.family.b, 'a': it.family.a}
            for it in session.items.all()
        ]
        theta, se, rating, result_grade, _ = score_assessment(items_data)

        # Decision rule: confirmed if result_grade >= claimed_grade, else unconfirmed
        GRADE_ORDER = {Grade.INTERN: 1, Grade.JUNIOR: 2, Grade.MIDDLE: 3, Grade.SENIOR: 4}
        claimed_val = GRADE_ORDER.get(session.claimed_grade, 2)
        achieved_val = GRADE_ORDER.get(result_grade, 2)

        if achieved_val >= claimed_val:
            decision = GradeDecision.CONFIRMED
            assigned_grade = session.claimed_grade
            league_status = LeagueStatus.CONFIRMED
        else:
            decision = GradeDecision.UNCONFIRMED
            assigned_grade = session.claimed_grade
            # Profile NOT hidden! Unconfirmed status, stays visible but deranked
            league_status = LeagueStatus.UNCONFIRMED

        session.theta = theta
        session.se = se
        session.rating = rating
        session.result_grade = assigned_grade
        session.decision = decision
        session.status = AssessmentStatus.FINISHED
        session.finished_at = now
        session.save()

        # Update or create LeagueMembership
        cooldown_days = settings.GRADE_RETRY_COOLDOWN_DAYS
        next_attempt = now + timedelta(days=cooldown_days)

        membership, _ = LeagueMembership.objects.get_or_create(
            candidate=request.user,
            specialization=session.specialization,
            defaults={
                'grade': assigned_grade,
                'status': league_status,
                'theta': theta,
                'se': se,
                'rating': rating,
                'strength': max(0.0, min(100.0, 50.0 + theta * 25.0)),
                'confirmed_at': now if decision == GradeDecision.CONFIRMED else None,
                'next_attempt_at': next_attempt,
            }
        )
        membership.grade = assigned_grade
        membership.status = league_status
        membership.theta = theta
        membership.se = se
        membership.rating = rating
        membership.strength = max(0.0, min(100.0, 50.0 + theta * 25.0))
        membership.next_attempt_at = next_attempt
        if decision == GradeDecision.CONFIRMED:
            membership.confirmed_at = now
        membership.save()

        return Response({
            'done': True,
            'result': AssessmentResultSerializer(session).data
        })


class AssessmentResultView(views.APIView):
    permission_classes = [IsCandidate]
    serializer_class = AssessmentResultSerializer

    @extend_schema(responses={200: AssessmentResultSerializer})
    def get(self, request, pk):
        session = AssessmentSession.objects.filter(id=pk, candidate=request.user).first()
        if not session or session.status != AssessmentStatus.FINISHED:
            raise FSPAPIError('not_finished', 'Not finished', 'Assessment is not finished yet', 400)
        
        return Response(AssessmentResultSerializer(session).data)
