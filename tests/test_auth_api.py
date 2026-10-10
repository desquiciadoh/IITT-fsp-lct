"""Tests for Authentication, Email Verification, Demo Persona, Time Travel, and Reset (G1, G2, G4, B3, B25)."""

import pytest
from assessment.models import AssessmentSession, LeagueMembership
from core.enums import AssessmentStatus, Grade, LeagueStatus, Specialization, UserRole
from django.core import signing
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="newcandidate@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
    )
    return user


@pytest.fixture
def demo_candidate_user(db):
    user = User.objects.create_user(
        email="demo_user@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        is_demo=True,
        email_verified_at=timezone.now(),
    )
    return user


@pytest.mark.django_db
class TestAuthAndVerification:
    def test_register_returns_verify_link_in_demo_mode(self, client, settings):
        settings.DEMO_MODE = True
        payload = {
            "email": "demo_applicant@example.com",
            "password": "password123",
            "role": "candidate",
        }
        res = client.post("/api/auth/register", payload, format="json")
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "demo_applicant@example.com"
        assert data["role"] == "candidate"
        assert "verify_link" in data
        assert "/verify-email?token=" in data["verify_link"]

    def test_verify_email_success(self, client, candidate_user):
        assert candidate_user.email_verified_at is None
        token = signing.dumps({"user_id": str(candidate_user.id)}, salt="email-verify")

        res = client.post("/api/auth/verify-email", {"token": token}, format="json")
        assert res.status_code == 204

        candidate_user.refresh_from_db()
        assert candidate_user.email_verified_at is not None
        assert candidate_user.is_email_verified is True

    def test_verify_email_invalid_token(self, client):
        res = client.post("/api/auth/verify-email", {"token": "invalid-token-123"}, format="json")
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_token"

    def test_verify_email_validation_missing_token(self, client):
        res = client.post("/api/auth/verify-email", {}, format="json")
        assert res.status_code == 422
        assert res.json()["code"] == "validation_failed"

    def test_login_rate_throttling(self, client, candidate_user):
        from django.core.cache import cache

        cache.clear()

        payload = {"email": candidate_user.email, "password": "wrongpassword"}
        for _ in range(10):
            res = client.post("/api/auth/login", payload, format="json")
            assert res.status_code == 401

        # The 11th request must get 429 with Retry-After header
        res_11 = client.post("/api/auth/login", payload, format="json")
        assert res_11.status_code == 429
        assert "Retry-After" in res_11.headers


@pytest.mark.django_db
class TestDemoResetAndTimeTravel:
    def test_time_travel_success(self, client, demo_candidate_user, settings):
        settings.DEMO_MODE = True
        client.force_authenticate(user=demo_candidate_user)

        res = client.post("/api/demo/time-travel", {"days": 15}, format="json")
        assert res.status_code == 200
        assert res.json()["clock_offset_days"] == 15

        demo_candidate_user.refresh_from_db()
        assert demo_candidate_user.clock_offset_days == 15

    def test_time_travel_sets_offset_directly_without_accumulation(
        self, client, demo_candidate_user, settings
    ):
        settings.DEMO_MODE = True
        client.force_authenticate(user=demo_candidate_user)

        res1 = client.post("/api/demo/time-travel", {"days": 10}, format="json")
        assert res1.status_code == 200
        assert res1.json()["clock_offset_days"] == 10

        # Next call should set offset directly to 15, NOT add to 25
        res2 = client.post("/api/demo/time-travel", {"days": 15}, format="json")
        assert res2.status_code == 200
        assert res2.json()["clock_offset_days"] == 15

        # Zero offset should work and set 0
        res3 = client.post("/api/demo/time-travel", {"days": 0}, format="json")
        assert res3.status_code == 200
        assert res3.json()["clock_offset_days"] == 0

    def test_time_travel_forbidden_for_non_demo_user(self, client, candidate_user, settings):
        settings.DEMO_MODE = True
        assert candidate_user.is_demo is False
        client.force_authenticate(user=candidate_user)

        res = client.post("/api/demo/time-travel", {"days": 10}, format="json")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden"

    def test_time_travel_validation_boundaries(self, client, demo_candidate_user, settings):
        settings.DEMO_MODE = True
        client.force_authenticate(user=demo_candidate_user)

        # Negative days
        res = client.post("/api/demo/time-travel", {"days": -1}, format="json")
        assert res.status_code == 422

        # Too large
        res = client.post("/api/demo/time-travel", {"days": 500}, format="json")
        assert res.status_code == 422

        # Non-integer
        res = client.post("/api/demo/time-travel", {"days": "abc"}, format="json")
        assert res.status_code == 422

    def test_demo_reset_clears_clock_offset_and_cooldowns(
        self, client, demo_candidate_user, settings
    ):
        settings.DEMO_MODE = True
        demo_candidate_user.clock_offset_days = 25
        demo_candidate_user.save()

        # Create active assessment session and cooldown membership
        session = AssessmentSession.objects.create(
            candidate=demo_candidate_user,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            status=AssessmentStatus.IN_PROGRESS,
        )
        membership = LeagueMembership.objects.create(
            candidate=demo_candidate_user,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.UNCONFIRMED,
            next_attempt_at=timezone.now() + timezone.timedelta(days=30),
        )

        client.force_authenticate(user=demo_candidate_user)
        res = client.post("/api/demo/reset", format="json")
        assert res.status_code == 200
        assert res.json()["clock_offset_days"] == 0

        demo_candidate_user.refresh_from_db()
        assert demo_candidate_user.clock_offset_days == 0

        # Assessment sessions wiped
        assert AssessmentSession.objects.filter(id=session.id).exists() is False

        membership.refresh_from_db()
        assert membership.next_attempt_at is None

    def test_demo_reset_restores_seeded_persona_data(self, client, settings):
        from core.demo_data import reset_demo_persona
        from profiles.models import CandidateProfile

        settings.DEMO_MODE = True

        anna = User.objects.create_user(
            email="anna.fsp@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
            is_demo=True,
            email_verified_at=timezone.now(),
        )
        # Initialize as seeded
        reset_demo_persona(anna)

        # Tamper with Anna's data as if user played around in demo
        profile = CandidateProfile.objects.get(user=anna)
        profile.full_name = "Modified Name"
        profile.salary_min = 400000
        profile.salary_max = 500000
        profile.open_to_offers = False
        profile.save()

        session = AssessmentSession.objects.create(
            candidate=anna,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.SENIOR,
            status=AssessmentStatus.IN_PROGRESS,
        )
        anna.clock_offset_days = 42
        anna.save()

        client.force_authenticate(user=anna)
        res = client.post("/api/demo/reset", format="json")
        assert res.status_code == 200
        assert res.json()["clock_offset_days"] == 0

        anna.refresh_from_db()
        assert anna.clock_offset_days == 0

        # Wiped demo assessment sessions
        assert AssessmentSession.objects.filter(id=session.id).exists() is False

        # Restored seeded persona profile
        profile.refresh_from_db()
        assert profile.full_name == "Анна Воронова"
        assert profile.salary_min == 290000
        assert profile.public_id == "C-7F3A2B"
        assert profile.open_to_offers is True

        # Restored league membership
        membership = LeagueMembership.objects.get(
            candidate=anna, specialization=Specialization.BACKEND
        )
        assert membership.status == LeagueStatus.CONFIRMED
        assert membership.grade == Grade.SENIOR
        assert membership.rating == 1250
        assert membership.strength == 95.0

    def test_demo_reset_forbidden_for_non_demo_user(self, client, candidate_user, settings):
        settings.DEMO_MODE = True
        assert candidate_user.is_demo is False
        client.force_authenticate(user=candidate_user)

        res = client.post("/api/demo/reset", format="json")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden"

    def test_demo_reset_disabled_when_demo_mode_false(self, client, demo_candidate_user, settings):
        settings.DEMO_MODE = False
        client.force_authenticate(user=demo_candidate_user)

        res = client.post("/api/demo/reset", format="json")
        assert res.status_code == 403
        assert res.json()["code"] == "forbidden"
