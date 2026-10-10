"""Unit and integration tests for Task N6 (Identity & Profile validation)."""

import uuid

import pytest
from core.enums import Specialization, UserRole
from django.core import mail
from django.db import IntegrityError
from identity.models import User
from matching.models import Company
from profiles.models import CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="n6_candidate@example.com",
        password="secretpassword",
        role=UserRole.CANDIDATE,
    )
    profile = CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="N6 Candidate",
        specialization=Specialization.BACKEND,
    )
    return user, profile


@pytest.mark.django_db
class TestN6IdentityEmailVerification:
    def test_registration_outside_demo_mode_sends_email_via_smtp(self, client, settings):
        settings.DEMO_MODE = False
        settings.PUBLIC_BASE_URL = "http://localhost:8000"
        mail.outbox.clear()

        payload = {
            "email": "fresh_user@example.com",
            "password": "password123",
            "role": "candidate",
        }
        res = client.post("/api/auth/register", payload, format="json")
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "fresh_user@example.com"
        assert data["email_verified"] is False
        assert "verify_link" not in data

        user = User.objects.get(email="fresh_user@example.com")
        assert user.is_email_verified is False
        assert user.email_verified_at is None

        # Check SMTP email was dispatched
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == ["fresh_user@example.com"]
        assert "Подтверждение email" in msg.subject
        assert "http://localhost:8000/verify-email?token=" in msg.body

        # Extract token from the message body
        import re
        match = re.search(r"token=([A-Za-z0-9_:\.\-]+)", msg.body)
        assert match is not None
        token = match.group(1)

        # Verify using the token
        verify_res = client.post("/api/auth/verify-email", {"token": token}, format="json")
        assert verify_res.status_code == 204

        user.refresh_from_db()
        assert user.is_email_verified is True
        assert user.email_verified_at is not None

    def test_registration_in_demo_mode_does_not_send_email_and_provides_verify_link(
        self, client, settings
    ):
        settings.DEMO_MODE = True
        mail.outbox.clear()

        payload = {
            "email": "demo_user_n6@example.com",
            "password": "password123",
            "role": "candidate",
        }
        res = client.post("/api/auth/register", payload, format="json")
        assert res.status_code == 201
        data = res.json()
        assert data["email_verified"] is True
        assert "verify_link" in data
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestN6ProfileValidation:
    def test_salary_min_must_be_positive(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {"salary_min": 0, "salary_max": 100000},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field") == "salary_min" for e in res.json().get("errors", []))

    def test_salary_min_greater_than_salary_max_fails(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {"salary_min": 150000, "salary_max": 100000},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field") == "salary_min" for e in res.json().get("errors", []))

    def test_salary_floor_greater_than_salary_min_fails(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {"salary_min": 100000, "salary_max": 200000, "salary_floor": 120000},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field") == "salary_floor" for e in res.json().get("errors", []))

    def test_salary_floor_zero_fails(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {"salary_min": 100000, "salary_max": 200000, "salary_floor": 0},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field") == "salary_floor" for e in res.json().get("errors", []))

    def test_valid_salary_range_succeeds(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {
                "salary_min": 100000,
                "salary_max": 150000,
                "salary_floor": 90000,
                "salary_type": "net",
            },
            format="json",
        )
        assert res.status_code == 200
        assert res.data["salary_min"] == 100000
        assert res.data["salary_max"] == 150000
        assert res.data["salary_floor"] == 90000
        assert res.data["salary_type"] == "net"

    def test_blocked_company_ids_invalid_uuid(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)

        res = client.put(
            "/api/candidates/me",
            {"blocked_company_ids": ["not-a-valid-uuid"]},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field", "").startswith("blocked_company_ids") for e in res.json().get("errors", []))

    def test_blocked_company_ids_non_existent_company(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)
        non_existent_id = str(uuid.uuid4())

        res = client.put(
            "/api/candidates/me",
            {"blocked_company_ids": [non_existent_id]},
            format="json",
        )
        assert res.status_code == 422
        assert any(e.get("field") == "blocked_company_ids" for e in res.json().get("errors", []))

    def test_blocked_company_ids_valid_and_deduplicated(self, client, candidate_user):
        user, _ = candidate_user
        client.force_authenticate(user)
        company = Company.objects.create(name="TechCorp")

        res = client.put(
            "/api/candidates/me",
            {"blocked_company_ids": [str(company.id), str(company.id)]},
            format="json",
        )
        assert res.status_code == 200
        assert res.data["blocked_company_ids"] == [str(company.id)]


@pytest.mark.django_db
class TestN6DatabaseCheckConstraints:
    def test_db_constraint_salary_min_positive(self, candidate_user):
        _, profile = candidate_user
        profile.salary_min = 0
        with pytest.raises(IntegrityError):
            profile.save()

    def test_db_constraint_salary_max_gte_min(self, candidate_user):
        _, profile = candidate_user
        profile.salary_min = 200000
        profile.salary_max = 100000
        with pytest.raises(IntegrityError):
            profile.save()

    def test_db_constraint_salary_type_valid(self, candidate_user):
        _, profile = candidate_user
        profile.salary_type = "invalid"
        with pytest.raises(IntegrityError):
            profile.save()

    def test_db_constraint_salary_floor_positive(self, candidate_user):
        _, profile = candidate_user
        profile.salary_floor = 0
        with pytest.raises(IntegrityError):
            profile.save()

    def test_db_constraint_salary_floor_lte_min(self, candidate_user):
        _, profile = candidate_user
        profile.salary_min = 100000
        profile.salary_floor = 150000
        with pytest.raises(IntegrityError):
            profile.save()
