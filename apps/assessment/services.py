"""Assessment service: CAT engine orchestration, session lifecycle, and IRT scoring."""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from assessment.engine import FAMILIES_REGISTRY, score_assessment
from assessment.models import AssessmentItem, AssessmentSession, ItemFamily, LeagueMembership
from core.enums import (
    AssessmentStatus,
    Grade,
    GradeDecision,
    LeagueStatus,
    Specialization,
)
from core.errors import (
    AssessmentInProgress,
    CooldownActive,
    FSPAPIError,
    ItemNotCurrent,
)
from fsp_sync.services import recompute_strength
from outreach.events import publish_domain_event

if TYPE_CHECKING:
    import uuid
    from identity.models import User

logger = logging.getLogger(__name__)

GRADE_ORDER = {
    Grade.INTERN: 1,
    Grade.JUNIOR: 2,
    Grade.MIDDLE: 3,
    Grade.SENIOR: 4,
}


def get_current_time_for_user(user) -> timezone.datetime:
    """Return current time adjusted for user's clock offset in DEMO_MODE.

    Used ONLY for cooldown comparisons to prevent corrupting stored timestamps.
    """
    now = timezone.now()
    if settings.DEMO_MODE and getattr(user, 'clock_offset_days', 0):
        now += timedelta(days=user.clock_offset_days)
    return now


class AssessmentService:
    """Manages the full lifecycle of an assessment session.

    Enforces invariants:
    1. Only one in-progress session per candidate per specialization.
    2. Stale sessions (>24h) auto-expire.
    3. Item deadlines are enforced server-side.
    4. Cooldown applied ONLY after a failed/unconfirmed attempt.
    5. FSP boost is preserved during league membership updates.
    """

    @staticmethod
    @transaction.atomic
    def start_assessment(
        user: User,
        specialization: str,
        claimed_grade: str,
        mode: str = 'full',
    ) -> AssessmentSession:
        now_real = timezone.now()
        now_demo = get_current_time_for_user(user)

        # 1. Check cooldown (compared using demo clock for time-travel testing)
        membership = LeagueMembership.objects.filter(
            candidate=user,
            specialization=specialization,
        ).first()
        if membership and membership.next_attempt_at and membership.next_attempt_at > now_demo:
            raise CooldownActive(membership.next_attempt_at.isoformat())

        # 2. Check active session per specialization; auto-expire stale sessions (>24h)
        stale_threshold = now_real - timedelta(hours=24)
        active_sessions = AssessmentSession.objects.select_for_update().filter(
            candidate=user,
            specialization=specialization,
            status=AssessmentStatus.IN_PROGRESS,
        )

        for s in active_sessions:
            if s.started_at < stale_threshold:
                s.status = AssessmentStatus.EXPIRED
                s.finished_at = now_real
                s.save(update_fields=['status', 'finished_at'])
            else:
                raise AssessmentInProgress()

        # 3. Pick families matching the requested specialization only
        families = [
            f for f in FAMILIES_REGISTRY.values()
            if f.spec == specialization
        ]
        if not families:
            raise FSPAPIError(
                'no_item_bank',
                'No item bank',
                f'No item families available for specialization: {specialization}',
                409,
            )

        # 4. Create the AssessmentSession
        session = AssessmentSession.objects.create(
            candidate=user,
            specialization=specialization,
            claimed_grade=claimed_grade,
            mode=mode,
            status=AssessmentStatus.IN_PROGRESS,
        )

        # 5. Seed items with HMAC
        item_seed_secret = getattr(settings, 'ITEM_SEED_SECRET', 'item-seed-secret-dev')
        for seq, family in enumerate(families, start=1):
            seed_raw = f"{item_seed_secret}:{session.id}:{family.family_id}:{seq}"
            seed = hmac.new(
                item_seed_secret.encode('utf-8'),
                seed_raw.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
            instance = family.generate(seed)

            item_family_obj, _ = ItemFamily.objects.get_or_create(
                id=family.family_id,
                defaults={
                    'specs': [specialization],
                    'topic': family.topic,
                    'format': 'choice',
                    'a': family.discrimination_a,
                    'b': family.difficulty_b,
                    'c': family.guessing_c,
                    'time_limit_s': family.time_limit_s,
                },
            )

            deadline = now_real + timedelta(seconds=instance.time_limit_s)
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
                key=instance.key,  # Server-side only
                fingerprint=instance.fingerprint,
                deadline_at=deadline,
            )

        return session

    @staticmethod
    @transaction.atomic
    def submit_answer(
        user: User,
        session_id: uuid.UUID,
        item_id: uuid.UUID,
        answer_val: str,
        integrity: dict | None = None,
    ) -> tuple[AssessmentSession, AssessmentItem | None, bool]:
        """Submit an answer to the current item.

        Returns (session, next_item, is_done).
        """
        session = AssessmentSession.objects.select_for_update().filter(
            id=session_id,
            candidate=user,
        ).first()
        if not session:
            raise FSPAPIError('not_found', 'Not found', 'Assessment session not found', 404)

        if session.status != AssessmentStatus.IN_PROGRESS:
            raise FSPAPIError(
                'assessment_expired',
                'Assessment closed',
                'Assessment is no longer in progress',
                400,
            )

        current_item = session.items.filter(answered_at__isnull=True).order_by('seq').first()
        if not current_item or str(current_item.id) != str(item_id):
            raise ItemNotCurrent()

        now_real = timezone.now()

        # Enforce deadline
        if current_item.deadline_at and now_real > current_item.deadline_at:
            current_item.answer = {'value': None, 'timed_out': True}
            current_item.correct = False
            current_item.answered_at = now_real
            current_item.save()

            for remaining in session.items.filter(answered_at__isnull=True):
                remaining.answer = {'value': None, 'timed_out': True}
                remaining.correct = False
                remaining.answered_at = now_real
                remaining.save()

            AssessmentService.finalize_assessment(session, user, timed_out=True)
            raise FSPAPIError(
                'deadline_exceeded',
                'Time expired',
                'Item deadline has passed',
                400,
            )

        correct = (answer_val == current_item.key)
        current_item.answer = {'value': answer_val}
        current_item.correct = correct
        current_item.answered_at = now_real
        current_item.integrity = integrity or {}
        current_item.save()

        next_item = session.items.filter(answered_at__isnull=True).order_by('seq').first()
        if next_item:
            return session, next_item, False

        # All items answered: finalize
        AssessmentService.finalize_assessment(session, user)
        session.refresh_from_db()
        return session, None, True

    @staticmethod
    @transaction.atomic
    def abandon_assessment(user: User, session_id: uuid.UUID) -> AssessmentSession:
        """Abandon an in-progress assessment."""
        session = AssessmentSession.objects.select_for_update().filter(
            id=session_id,
            candidate=user,
        ).first()
        if not session:
            raise FSPAPIError('not_found', 'Not found', 'Assessment session not found', 404)

        if session.status != AssessmentStatus.IN_PROGRESS:
            raise FSPAPIError(
                'invalid_state',
                'Invalid state',
                'Assessment session is not in progress',
                400,
            )

        now_real = timezone.now()
        for remaining in session.items.filter(answered_at__isnull=True):
            remaining.answer = {'value': None, 'abandoned': True}
            remaining.correct = False
            remaining.answered_at = now_real
            remaining.save()

        AssessmentService.finalize_assessment(session, user, timed_out=True)
        session.refresh_from_db()
        return session

    @staticmethod
    def finalize_assessment(
        session: AssessmentSession,
        user: User,
        timed_out: bool = False,
    ) -> AssessmentSession:
        """Compute IRT score, update session, and adjust LeagueMembership."""
        now_real = timezone.now()
        items_data = [
            {'correct': it.correct, 'b': it.family.b, 'a': it.family.a}
            for it in session.items.all()
        ]
        theta, se, rating, result_grade, _ = score_assessment(items_data)

        claimed_val = GRADE_ORDER.get(session.claimed_grade, 2)
        achieved_val = GRADE_ORDER.get(result_grade, 2)

        if not timed_out and achieved_val >= claimed_val:
            decision = GradeDecision.CONFIRMED
            assigned_grade = session.claimed_grade
            league_status = LeagueStatus.CONFIRMED
        else:
            decision = GradeDecision.UNCONFIRMED
            assigned_grade = session.claimed_grade
            league_status = LeagueStatus.UNCONFIRMED

        session.theta = theta
        session.se = se
        session.rating = rating
        session.result_grade = assigned_grade
        session.decision = decision
        session.status = AssessmentStatus.FINISHED
        session.finished_at = now_real
        session.save()

        # Cooldown applied ONLY after a failed/unconfirmed claim
        cooldown_days = getattr(settings, 'GRADE_RETRY_COOLDOWN_DAYS', 30)
        next_attempt = (
            now_real + timedelta(days=cooldown_days)
            if decision == GradeDecision.UNCONFIRMED
            else None
        )

        base_strength = max(0.0, min(100.0, 50.0 + theta * 25.0))

        membership, _ = LeagueMembership.objects.get_or_create(
            candidate=user,
            specialization=session.specialization,
            defaults={
                'grade': assigned_grade,
                'status': league_status,
                'theta': theta,
                'se': se,
                'rating': rating,
                'base_strength': base_strength,
                'strength': base_strength,
                'confirmed_at': now_real if decision == GradeDecision.CONFIRMED else None,
                'next_attempt_at': next_attempt,
            },
        )
        membership.grade = assigned_grade
        membership.status = league_status
        membership.theta = theta
        membership.se = se
        membership.rating = rating
        membership.base_strength = base_strength
        membership.strength = base_strength
        membership.next_attempt_at = next_attempt
        if decision == GradeDecision.CONFIRMED:
            membership.confirmed_at = now_real
        membership.save()

        # Preserve and reapply FSP boost without wiping it
        recompute_strength(user)
        membership.refresh_from_db()

        publish_domain_event('league.updated', {
            'candidate_id': str(user.id),
            'specialization': session.specialization,
            'grade': assigned_grade,
            'status': league_status,
            'rating': rating,
            'strength': membership.strength,
        })

        return session

    @staticmethod
    @transaction.atomic
    def fallback(
        user: User,
        session_id: uuid.UUID,
        mode: str = 'instant',
    ) -> tuple[AssessmentSession, bool]:
        """Process fallback for an unconfirmed assessment.

        Returns (session, is_new_session).
        If mode == 'instant', confirms candidate at lower grade and returns (original_session, False).
        If mode == 'short_test', starts a new assessment session at lower grade and returns (new_session, True).
        """
        session = AssessmentSession.objects.select_for_update().filter(
            id=session_id,
            candidate=user,
        ).first()
        if not session:
            raise FSPAPIError('not_found', 'Not found', 'Assessment session not found', 404)

        if session.status != AssessmentStatus.FINISHED or session.decision != GradeDecision.UNCONFIRMED:
            raise FSPAPIError(
                'fallback_not_available',
                'Fallback not available',
                'Fallback is only available for finished unconfirmed assessments',
                400,
            )

        lower_grades = {
            Grade.SENIOR: Grade.MIDDLE,
            Grade.MIDDLE: Grade.JUNIOR,
            Grade.JUNIOR: Grade.INTERN,
        }
        lower_grade = lower_grades.get(session.claimed_grade)
        if not lower_grade:
            raise FSPAPIError(
                'fallback_not_available',
                'Fallback not available',
                'No lower grade available for fallback',
                400,
            )

        if mode == 'instant':
            session.result_grade = lower_grade
            session.decision = GradeDecision.CONFIRMED
            session.save(update_fields=['result_grade', 'decision'])

            now_real = timezone.now()
            membership, _ = LeagueMembership.objects.get_or_create(
                candidate=user,
                specialization=session.specialization,
                defaults={
                    'grade': lower_grade,
                    'status': LeagueStatus.CONFIRMED,
                    'theta': session.theta,
                    'se': session.se,
                    'rating': session.rating,
                    'base_strength': 50.0,
                    'strength': 50.0,
                    'confirmed_at': now_real,
                },
            )
            membership.grade = lower_grade
            membership.status = LeagueStatus.CONFIRMED
            membership.confirmed_at = now_real
            membership.next_attempt_at = None
            membership.save()

            recompute_strength(user)
            return session, False
        elif mode == 'short_test':
            membership = LeagueMembership.objects.filter(
                candidate=user,
                specialization=session.specialization,
            ).first()
            if membership and membership.next_attempt_at:
                membership.next_attempt_at = None
                membership.save(update_fields=['next_attempt_at'])

            new_session = AssessmentService.start_assessment(
                user=user,
                specialization=session.specialization,
                claimed_grade=lower_grade,
                mode='express',
            )
            return new_session, True
        else:
            raise FSPAPIError(
                'invalid_mode',
                'Invalid fallback mode',
                f'Unknown mode: {mode}',
                400,
            )

