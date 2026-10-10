"""Tests for Task R18: Pool and search pagination validation (page >= 1, 1 <= size <= 100)."""

import pytest
from core.enums import ConsentType, Grade, LeagueStatus, SalaryType, Specialization, UserRole
from django.utils import timezone
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position
from profiles.models import CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def employer_and_position(db):
    employer = User.objects.create_user(
        email="employer_r18@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="R18 Test Corp", contact_email="hr@r18.com")
    CompanyMember.objects.create(company=company, user=employer)
    position = Position.objects.create(
        company=company,
        title="Backend Dev",
        specialization=Specialization.BACKEND,
        grades=[Grade.MIDDLE],
        salary_min=150000,
        salary_max=220000,
        salary_type=SalaryType.GROSS,
    )

    candidate = User.objects.create_user(
        email="cand_r18@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=candidate,
        public_id=generate_public_id(),
        full_name="Test Candidate",
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        salary_min=120000,
        salary_max=180000,
        salary_type=SalaryType.GROSS,
        open_to_offers=True,
    )
    Consent.objects.create(
        user=candidate,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    from assessment.models import LeagueMembership

    LeagueMembership.objects.create(
        candidate=candidate,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1100,
        strength=80.0,
    )

    return employer, position


@pytest.mark.django_db
class TestPaginationR18:
    def test_search_valid_pagination(self, employer_and_position):
        employer, _ = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        res = client.get("/api/talent/search?page=1&size=20")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 1
        assert "items" in data

        res2 = client.get("/api/talent/search?page=1&size=100")
        assert res2.status_code == 200

        res3 = client.get("/api/talent/search?page=1&page_size=50")
        assert res3.status_code == 200

    def test_search_invalid_page(self, employer_and_position):
        employer, _ = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        for invalid_page in [0, -1, "abc"]:
            res = client.get(f"/api/talent/search?page={invalid_page}")
            assert res.status_code == 422
            assert res.json()["code"] == "validation_failed"

    def test_search_invalid_size(self, employer_and_position):
        employer, _ = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        # size=0 must return 422, not 500 ZeroDivisionError
        for invalid_size in [0, -5, 101, 500, "xyz"]:
            res = client.get(f"/api/talent/search?size={invalid_size}")
            assert res.status_code == 422
            assert res.json()["code"] == "validation_failed"

    def test_pool_valid_pagination(self, employer_and_position):
        employer, position = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        res = client.get(f"/api/positions/{position.id}/pool?page=1&size=20")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 1
        assert "items" in data

        res2 = client.get(f"/api/positions/{position.id}/pool?page=1&size=100")
        assert res2.status_code == 200

    def test_pool_invalid_page(self, employer_and_position):
        employer, position = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        for invalid_page in [0, -1, "abc"]:
            res = client.get(f"/api/positions/{position.id}/pool?page={invalid_page}")
            assert res.status_code == 422
            assert res.json()["code"] == "validation_failed"

    def test_pool_invalid_size(self, employer_and_position):
        employer, position = employer_and_position
        client = APIClient()
        client.force_authenticate(user=employer)

        # size=0 must return 422, not 500 ZeroDivisionError
        for invalid_size in [0, -1, 101, 200, "xyz"]:
            res = client.get(f"/api/positions/{position.id}/pool?size={invalid_size}")
            assert res.status_code == 422
            assert res.json()["code"] == "validation_failed"
