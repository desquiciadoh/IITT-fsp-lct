"""Test Grade Immutability: FSP achievements NEVER alter candidate Grade.

INVARIANT: A candidate's grade (Intern, Junior, Middle, Senior) is determined
EXCLUSIVELY by the adaptive qualification assessment (CAT).
FSP achievements (sports ranks, tournament wins) influence Profile Strength
and ranking within the League, but CANNOT change or elevate a candidate's Grade.
"""
import pytest
from datetime import date
from django.utils import timezone

from identity.models import User
from assessment.models import LeagueMembership
from fsp_sync.models import FSPLink, FSPResult
from fsp_sync.views import sync_candidate_fsp_data
from core.enums import (
    Discipline,
    Grade,
    LeagueStatus,
    PlacementTier,
    Specialization,
    SportsRank,
    UserRole,
)


@pytest.fixture
def junior_candidate(db):
    user = User.objects.create_user(
        email='junior.champ@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    # Confirmed Junior from CAT test
    lm = LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade=Grade.JUNIOR,
        status=LeagueStatus.CONFIRMED,
        theta=-0.1,
        rating=980,
        strength=50.0,
        confirmed_at=timezone.now(),
    )
    return user, lm


@pytest.mark.django_db
class TestGradeImmutability:

    def test_fsp_achievements_boost_strength_not_grade(self, junior_candidate):
        """FSP Master of Sports and 1st place award increases strength, but Grade stays Junior."""
        user, league_membership = junior_candidate

        initial_grade = league_membership.grade
        initial_strength = league_membership.strength
        assert initial_grade == Grade.JUNIOR

        # Candidate links FSP ID with top achievements: MS rank + 1st place
        link = FSPLink.objects.create(
            candidate=user,
            participant_id='FSP-999999',
            sports_rank=SportsRank.MS,
        )
        FSPResult.objects.create(
            candidate=user,
            event_id='NATIONAL-GOLD-2025',
            event_name='Чемпионат России по СП (Золото)',
            discipline=Discipline.ALGORITHMIC,
            date=date(2025, 11, 20),
            placement=1,
            tier=PlacementTier.WINNER,
            participants_total=300,
        )

        # Trigger sync/recalculate
        sync_candidate_fsp_data(user, 'FSP-999999')

        league_membership.refresh_from_db()

        # Grade MUST remain unchanged!
        assert league_membership.grade == Grade.JUNIOR, (
            f"INVARIANT VIOLATION: Grade changed from {initial_grade} to {league_membership.grade}!"
        )

        # Strength MUST increase (ranking boost)
        assert league_membership.strength > initial_strength, (
            "FSP achievements should boost candidate strength within the league."
        )

    def test_unconfirmed_grade_stays_unconfirmed_with_fsp(self, db):
        """Candidate who failed CAT test remains UNCONFIRMED even with FSP achievements."""
        user = User.objects.create_user(
            email='unconfirmed.fsp@example.com',
            password='password123',
            role=UserRole.CANDIDATE,
            email_verified_at=timezone.now(),
        )
        lm = LeagueMembership.objects.create(
            candidate=user,
            specialization=Specialization.BACKEND,
            grade=Grade.SENIOR,
            status=LeagueStatus.UNCONFIRMED,
            theta=0.2,
            rating=1040,
            strength=40.0,
        )

        # Link FSP achievements
        sync_candidate_fsp_data(user, 'FSP-000123')

        lm.refresh_from_db()

        # Status must stay UNCONFIRMED
        assert lm.status == LeagueStatus.UNCONFIRMED
        assert lm.grade == Grade.SENIOR  # Not promoted, not confirmed

    def test_sync_is_idempotent_strength_does_not_inflate(self, junior_candidate):
        """Calling FSP sync multiple times does NOT inflate strength (B10)."""
        user, league_membership = junior_candidate

        FSPLink.objects.create(
            candidate=user,
            participant_id='FSP-999999',
            sports_rank=SportsRank.MS,
        )
        FSPResult.objects.create(
            candidate=user,
            event_id='NATIONAL-GOLD-2025',
            event_name='Чемпионат России по СП (Золото)',
            discipline=Discipline.ALGORITHMIC,
            date=date(2025, 11, 20),
            placement=1,
            tier=PlacementTier.WINNER,
            participants_total=300,
        )

        # First sync
        sync_candidate_fsp_data(user, 'FSP-999999')
        league_membership.refresh_from_db()
        first_sync_strength = league_membership.strength
        assert first_sync_strength == 55.0  # 50.0 base + 5.0 boost

        # Second sync
        sync_candidate_fsp_data(user, 'FSP-999999')
        league_membership.refresh_from_db()
        assert league_membership.strength == first_sync_strength, (
            "FSP sync must be idempotent: multiple syncs must not inflate profile strength!"
        )
