"""Tests for R12: Request validation and fallback rules.

- StartAssessmentSerializer: required fields, and mode from AssessmentMode.choices.
- AnswerRequestSerializer.validate() requires option_id or value.
- Short-test fallback session gets kind=FALLBACK, counts_as_attempt=False.
- Instant-fallback membership get_or_create derives base_strength from theta.
"""

import pytest
from assessment.models import AssessmentSession, LeagueMembership
from assessment.services import AssessmentService
from core.enums import (
    AssessmentKind,
    AssessmentMode,
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
        email="r12_candidate@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def auth_client(candidate_user):
    client = APIClient()
    client.force_authenticate(user=candidate_user)
    return client


@pytest.mark.django_db
class TestRequestValidationAndFallback:
    def test_start_assessment_serializer_required_fields(self, auth_client):
        # Empty payload should fail validation because specialization and claimed_grade are required
        res = auth_client.post("/api/assessments", {}, format="json")
        assert res.status_code == 422
        body = res.json()
        error_fields = [e["field"] for e in body["errors"]]
        assert "specialization" in error_fields
        assert "claimed_grade" in error_fields

    def test_start_assessment_serializer_mode_choices(self, auth_client):
        # 'trial' should be rejected
        res = auth_client.post(
            "/api/assessments",
            {
                "specialization": Specialization.BACKEND,
                "claimed_grade": Grade.MIDDLE,
                "mode": "trial",
            },
            format="json",
        )
        assert res.status_code == 422
        error_fields = [e["field"] for e in res.json()["errors"]]
        assert "mode" in error_fields

        # 'express' should be accepted
        res_ok = auth_client.post(
            "/api/assessments",
            {
                "specialization": Specialization.BACKEND,
                "claimed_grade": Grade.MIDDLE,
                "mode": AssessmentMode.EXPRESS,
            },
            format="json",
        )
        assert res_ok.status_code == 201
        assert res_ok.json()["mode"] == AssessmentMode.EXPRESS

    def test_answer_request_serializer_requires_option_or_value(self, candidate_user, auth_client):
        session = AssessmentService.start_assessment(
            candidate_user, Specialization.BACKEND, Grade.MIDDLE
        )
        item = session.items.order_by("seq").first()

        # Both option_id and value missing
        res = auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(item.id)},
            format="json",
        )
        assert res.status_code == 422

        # Both option_id and value empty string
        res_empty = auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(item.id), "option_id": "", "value": ""},
            format="json",
        )
        assert res_empty.status_code == 422

        # Valid with option_id
        res_valid = auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(item.id), "option_id": item.key},
            format="json",
        )
        assert res_valid.status_code == 200

    def test_short_test_fallback_kind_and_counts_as_attempt(self, candidate_user, auth_client):
        # Create an unconfirmed finished Senior session
        session = AssessmentService.start_assessment(
            candidate_user, Specialization.BACKEND, Grade.SENIOR
        )
        items = list(session.items.order_by("seq"))
        # Answer all items wrong so achieved grade is lower (e.g. Intern)
        for it in items:
            wrong_opt = next(o["id"] for o in it.view["options"] if o["id"] != it.key)
            auth_client.post(
                f"/api/assessments/{session.id}/answers",
                {"item_id": str(it.id), "option_id": wrong_opt},
                format="json",
            )
        session.refresh_from_db()
        assert session.decision == GradeDecision.UNCONFIRMED

        # Request short_test fallback
        res = auth_client.post(
            f"/api/assessments/{session.id}/fallback",
            {"mode": "short_test"},
            format="json",
        )
        assert res.status_code == 201
        data = res.json()
        new_session = AssessmentSession.objects.get(id=data["id"])
        assert new_session.kind == AssessmentKind.FALLBACK
        assert new_session.counts_as_attempt is False

    def test_instant_fallback_derives_base_strength_from_theta(self, candidate_user, auth_client):
        # Create an unconfirmed finished Senior session with 1 correct answer (theta = 0.6)
        session = AssessmentService.start_assessment(
            candidate_user, Specialization.BACKEND, Grade.SENIOR
        )
        items = list(session.items.order_by("seq"))
        # First correct, second wrong
        auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(items[0].id), "option_id": items[0].key},
            format="json",
        )
        wrong_opt = next(o["id"] for o in items[1].view["options"] if o["id"] != items[1].key)
        auth_client.post(
            f"/api/assessments/{session.id}/answers",
            {"item_id": str(items[1].id), "option_id": wrong_opt},
            format="json",
        )
        session.refresh_from_db()
        assert session.theta is not None
        assert session.theta != 0.0

        expected_strength = max(0.0, min(100.0, 50.0 + session.theta * 25.0))
        # Verify expected strength is not the arbitrary default 50.0
        assert expected_strength != 50.0

        res = auth_client.post(
            f"/api/assessments/{session.id}/fallback",
            {"mode": "instant"},
            format="json",
        )
        assert res.status_code == 200

        membership = LeagueMembership.objects.get(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
        )
        assert membership.base_strength == pytest.approx(expected_strength, 0.01)
        assert membership.strength == pytest.approx(expected_strength, 0.01)
