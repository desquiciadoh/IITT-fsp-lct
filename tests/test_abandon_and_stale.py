"""Tests for R11: Abandon and stale rules (ARCHITECTURE §2.5).

- /finish and the stale-session sweep count as an attempt (finalize unconfirmed plus cooldown)
  only if at least 50% of items were answered. Otherwise the session becomes ABANDONED/EXPIRED
  with no cooldown.
- Use AssessmentStatus.ABANDONED.
- EligibilityView checks in-progress sessions per specialization.
"""

from datetime import timedelta

import pytest
from assessment.models import LeagueMembership
from assessment.services import AssessmentService
from core.enums import (
    AssessmentStatus,
    Grade,
    GradeDecision,
    Specialization,
    UserRole,
)
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    return User.objects.create_user(
        email="abandon_tester@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def auth_client(candidate_user):
    client = APIClient()
    client.force_authenticate(user=candidate_user)
    return client


def _start_session(cand, spec=Specialization.BACKEND, grade=Grade.SENIOR):
    return AssessmentService.start_assessment(cand, spec, grade)


@pytest.mark.django_db
class TestAbandonAndStaleRules:
    def test_finish_under_50_pct_answered_becomes_abandoned_no_cooldown(
        self, candidate_user, auth_client
    ):
        session = _start_session(candidate_user)
        # 0 items answered out of 2 (0% < 50%)
        res = auth_client.post(f"/api/assessments/{session.id}/finish")
        assert res.status_code == 200
        session.refresh_from_db()

        assert session.status == AssessmentStatus.ABANDONED
        assert session.counts_as_attempt is False

        # No cooldown on LeagueMembership
        membership = LeagueMembership.objects.filter(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
        ).first()
        assert membership is None or membership.next_attempt_at is None

        # Candidate can immediately start again
        elig_res = auth_client.get(
            f"/api/assessments/eligibility?specialization={Specialization.BACKEND}"
        )
        assert elig_res.status_code == 200
        assert elig_res.json()["can_start"] is True

    def test_finish_at_least_50_pct_answered_counts_as_attempt_and_sets_cooldown(
        self, candidate_user, auth_client
    ):
        session = _start_session(candidate_user)
        first_item = session.items.order_by("seq").first()

        # Answer 1 item out of 2 (50% >= 50%)
        ans_res = auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(first_item.id), "option_id": first_item.key},
            format="json",
        )
        assert ans_res.status_code == 200

        # Now finish/abandon early
        res = auth_client.post(f"/api/assessments/{session.id}/finish")
        assert res.status_code == 200
        session.refresh_from_db()

        assert session.status == AssessmentStatus.FINISHED
        assert session.decision == GradeDecision.UNCONFIRMED
        assert session.counts_as_attempt is True

        membership = LeagueMembership.objects.get(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
        )
        assert membership.next_attempt_at is not None

        # In cooldown
        elig_res = auth_client.get(
            f"/api/assessments/eligibility?specialization={Specialization.BACKEND}"
        )
        assert elig_res.status_code == 200
        assert elig_res.json()["can_start"] is False
        assert elig_res.json()["reason"] == "cooldown_active"

    def test_stale_sweep_under_50_pct_answered_becomes_expired_no_cooldown(self, candidate_user):
        session = _start_session(candidate_user)
        first_item = session.items.order_by("seq").first()
        # Expire deadline into the past
        first_item.deadline_at = timezone.now() - timedelta(seconds=120)
        first_item.save(update_fields=["deadline_at"])

        swept = AssessmentService.sweep_stale_sessions(grace_seconds=0)
        assert swept >= 1
        session.refresh_from_db()

        assert session.status == AssessmentStatus.EXPIRED
        assert session.counts_as_attempt is False

        membership = LeagueMembership.objects.filter(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
        ).first()
        assert membership is None or membership.next_attempt_at is None

    def test_stale_sweep_at_least_50_pct_answered_finalizes_unconfirmed_with_cooldown(
        self, candidate_user
    ):
        session = _start_session(candidate_user)
        items = list(session.items.order_by("seq"))
        first_item, second_item = items[0], items[1]

        # Answer first item
        now = timezone.now()
        first_item.answer = {"value": first_item.key}
        first_item.correct = True
        first_item.answered_at = now
        first_item.save()

        # Serve second item and expire its deadline
        second_item.served_at = now - timedelta(seconds=120)
        second_item.deadline_at = now - timedelta(seconds=60)
        second_item.save()

        swept = AssessmentService.sweep_stale_sessions(grace_seconds=0)
        assert swept >= 1
        session.refresh_from_db()

        assert session.status == AssessmentStatus.FINISHED
        assert session.decision == GradeDecision.UNCONFIRMED
        assert session.counts_as_attempt is True

        membership = LeagueMembership.objects.get(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
        )
        assert membership.next_attempt_at is not None

    def test_eligibility_view_checks_in_progress_per_specialization(
        self, candidate_user, auth_client
    ):
        # Candidate has in-progress session in BACKEND
        backend_session = _start_session(candidate_user, spec=Specialization.BACKEND)

        # Checking BACKEND -> cannot start, active session id returned
        res_backend = auth_client.get(
            f"/api/assessments/eligibility?specialization={Specialization.BACKEND}"
        )
        assert res_backend.status_code == 200
        data_backend = res_backend.json()
        assert data_backend["can_start"] is False
        assert data_backend["active_session_id"] == str(backend_session.id)

        # Checking FRONTEND -> can start! (no in-progress session for FRONTEND)
        res_frontend = auth_client.get(
            f"/api/assessments/eligibility?specialization={Specialization.FRONTEND}"
        )
        assert res_frontend.status_code == 200
        data_frontend = res_frontend.json()
        assert data_frontend["can_start"] is True
        assert data_frontend.get("active_session_id") is None
