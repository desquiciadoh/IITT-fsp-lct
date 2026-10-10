"""Tests for Task N3: recompute_league(spec, grade) via engine adapter.

Covers:
1. Adapter percentile calculation with rank-based formulas and ties.
2. recompute_league updates all memberships in the specified league.
3. Idempotency of recompute_league.
4. Emitting league.updated domain events with candidate_id.
5. Automatic triggers after assessment finalization and FSP sync.
"""

import pytest
from assessment.engine_adapter import compute_league_percentiles
from assessment.models import AssessmentSession, ItemFamily, LeagueMembership
from assessment.services import AssessmentService, recompute_league
from core.enums import AssessmentMode, AssessmentStatus, Grade, GradeDecision, LeagueStatus, Specialization, UserRole
from fsp_sync.models import FSPResult
from fsp_sync.services import recompute_strength, sync_fsp_data
from identity.models import User
from outreach.events import register_subscriber, unregister_subscriber


@pytest.fixture
def candidate_factory(db):
    counter = 0

    def _create(email=None, **kwargs):
        nonlocal counter
        counter += 1
        mail = email or f"candidate_n3_{counter}@example.com"
        return User.objects.create_user(
            email=mail,
            password="password123",
            role=UserRole.CANDIDATE,
            **kwargs,
        )

    return _create


@pytest.mark.django_db
class TestN3EngineAdapterPercentiles:
    def test_compute_percentiles_empty(self):
        assert compute_league_percentiles([]) == {}

    def test_compute_percentiles_single_member(self):
        res = compute_league_percentiles([("u1", 0.5)])
        assert res == {"u1": 100.0}

    def test_compute_percentiles_distinct_scores(self):
        scores = [("u1", -1.0), ("u2", 0.0), ("u3", 1.0)]
        res = compute_league_percentiles(scores)
        assert res["u1"] == 33.3
        assert res["u2"] == 66.7
        assert res["u3"] == 100.0

    def test_compute_percentiles_ties_share_rank(self):
        scores = [("u1", -0.5), ("u2", 0.0), ("u3", 0.0), ("u4", 1.0)]
        res = compute_league_percentiles(scores)
        assert res["u1"] == 25.0
        # u2 and u3 tied at rank 3 out of 4 -> 75.0%
        assert res["u2"] == 75.0
        assert res["u3"] == 75.0
        assert res["u4"] == 100.0


@pytest.mark.django_db
class TestN3RecomputeLeague:
    def test_recompute_league_empty(self):
        updated = recompute_league(Specialization.BACKEND, Grade.SENIOR)
        assert updated == []

    def test_recompute_league_updates_all_members_in_league(self, candidate_factory):
        c1 = candidate_factory("c1@example.com")
        c2 = candidate_factory("c2@example.com")
        c3 = candidate_factory("c3@example.com")
        other_spec = candidate_factory("other@example.com")

        # 3 members in Backend/Middle
        m1 = LeagueMembership.objects.create(
            candidate=c1,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            theta=-0.5,
            rating=900,
        )
        m2 = LeagueMembership.objects.create(
            candidate=c2,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            theta=0.0,
            rating=1000,
        )
        m3 = LeagueMembership.objects.create(
            candidate=c3,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            theta=0.8,
            rating=1160,
        )

        # 1 member in Frontend/Middle (should not be touched)
        m_other = LeagueMembership.objects.create(
            candidate=other_spec,
            specialization=Specialization.FRONTEND,
            grade=Grade.MIDDLE,
            theta=0.5,
            rating=1100,
        )

        updated = recompute_league(Specialization.BACKEND, Grade.MIDDLE)
        assert len(updated) == 3

        m1.refresh_from_db()
        m2.refresh_from_db()
        m3.refresh_from_db()
        m_other.refresh_from_db()

        assert m1.percentile == 33.3
        assert m2.percentile == 66.7
        assert m3.percentile == 100.0
        assert m_other.percentile is None

    def test_recompute_league_is_idempotent(self, candidate_factory):
        c1 = candidate_factory("c1_idem@example.com")
        c2 = candidate_factory("c2_idem@example.com")

        m1 = LeagueMembership.objects.create(
            candidate=c1,
            specialization=Specialization.BACKEND,
            grade=Grade.JUNIOR,
            theta=0.2,
        )
        m2 = LeagueMembership.objects.create(
            candidate=c2,
            specialization=Specialization.BACKEND,
            grade=Grade.JUNIOR,
            theta=0.5,
        )

        # First run
        recompute_league(Specialization.BACKEND, Grade.JUNIOR)
        m1.refresh_from_db()
        m2.refresh_from_db()
        p1_first, p2_first = m1.percentile, m2.percentile

        # Second run
        recompute_league(Specialization.BACKEND, Grade.JUNIOR)
        m1.refresh_from_db()
        m2.refresh_from_db()
        assert m1.percentile == p1_first == 50.0
        assert m2.percentile == p2_first == 100.0

    def test_recompute_league_emits_league_updated_event(
        self, candidate_factory, django_capture_on_commit_callbacks
    ):
        c1 = candidate_factory("c1_evt@example.com")
        m1 = LeagueMembership.objects.create(
            candidate=c1,
            specialization=Specialization.BACKEND,
            grade=Grade.SENIOR,
            theta=1.2,
            rating=1240,
            strength=80.0,
        )

        sub = register_subscriber(user_id=c1.id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                recompute_league(Specialization.BACKEND, Grade.SENIOR)

            assert not sub.empty()
            item = sub.get_nowait()
            assert item["event"] == "league.updated"
            assert item["data"]["candidate_id"] == str(c1.id)
            assert item["data"]["specialization"] == Specialization.BACKEND
            assert item["data"]["grade"] == Grade.SENIOR
            assert item["data"]["percentile"] == 100.0
        finally:
            unregister_subscriber(sub)

    def test_trigger_after_finalize_assessment(self, candidate_factory):
        from assessment.engine_adapter import sync_families_to_db

        candidate = candidate_factory("c_final@example.com")
        sync_families_to_db()

        session = AssessmentSession.objects.create(
            candidate=candidate,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.JUNIOR,
            mode=AssessmentMode.EXPRESS,
            status=AssessmentStatus.IN_PROGRESS,
        )

        AssessmentService.finalize_assessment(session, candidate)
        membership = LeagueMembership.objects.get(
            candidate=candidate,
            specialization=Specialization.BACKEND,
        )
        assert membership.percentile is not None
        assert membership.percentile == 100.0

    def test_trigger_after_fsp_sync(self, candidate_factory):
        candidate = candidate_factory("c_fsp@example.com")
        lm = LeagueMembership.objects.create(
            candidate=candidate,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            theta=0.4,
            base_strength=60.0,
            strength=60.0,
        )

        # Candidate gets an FSP result
        FSPResult.objects.create(
            candidate=candidate,
            event_id="EV_N3_1",
            event_name="Championship",
            discipline="backend",
            date="2025-01-01",
            placement=1,
            tier="winner",
            participants_total=100,
            source_hash="hash1",
        )

        # Trigger recompute_strength
        recompute_strength(candidate)
        lm.refresh_from_db()
        assert lm.fsp_boost == 5.0
        assert lm.strength == 65.0
        assert lm.percentile is not None
        assert lm.percentile == 100.0
