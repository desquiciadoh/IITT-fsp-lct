"""Tests for R13: GET /assessments hides evidence[].correct while session is in progress."""

import pytest
from assessment.services import AssessmentService
from core.enums import AssessmentStatus, Grade, Specialization, UserRole
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    return User.objects.create_user(
        email="candidate_evidence@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def auth_client(candidate_user):
    c = APIClient()
    c.force_authenticate(user=candidate_user)
    return c


@pytest.mark.django_db
class TestAssessmentEvidenceVisibility:
    def test_in_progress_session_hides_evidence_correct(self, candidate_user, auth_client):
        # 1. Start assessment
        session = AssessmentService.start_assessment(
            user=candidate_user,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
        )
        assert session.status == AssessmentStatus.IN_PROGRESS

        # Answer one item so it has correct evaluated in DB
        first_item = session.items.order_by("seq").first()
        assert first_item is not None
        AssessmentService.submit_answer(
            user=candidate_user,
            session_id=session.id,
            item_id=first_item.id,
            answer_val=first_item.key,
        )
        first_item.refresh_from_db()
        assert first_item.correct is True

        # 2. GET /api/assessments
        res = auth_client.get("/api/assessments")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 1
        session_data = items[0]
        assert session_data["status"] == AssessmentStatus.IN_PROGRESS

        # Check evidence: 'correct' must NOT be revealed while in progress
        evidence = session_data.get("evidence", [])
        for ev in evidence:
            assert "correct" not in ev, f"Leaked 'correct' while in progress: {ev}"

        # 3. Finish the assessment
        AssessmentService.finalize_assessment(session, candidate_user)
        session.refresh_from_db()
        assert session.status == AssessmentStatus.FINISHED

        # 4. GET /api/assessments after finish
        res2 = auth_client.get("/api/assessments")
        assert res2.status_code == 200
        session_data2 = res2.json()["items"][0]
        assert session_data2["status"] == AssessmentStatus.FINISHED

        # Now 'correct' must be visible in evidence
        evidence2 = session_data2.get("evidence", [])
        assert len(evidence2) > 0
        for ev in evidence2:
            assert "correct" in ev, f"Missing 'correct' after finished: {ev}"
            assert isinstance(ev["correct"], bool)
