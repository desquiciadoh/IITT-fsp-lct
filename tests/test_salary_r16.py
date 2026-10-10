"""Tests for Task R16 (Salary invariants, DB constraints, and 422 salary_invalid errors)."""

import pytest
from assessment.models import LeagueMembership
from core.enums import (
    ConsentType,
    ContactChannel,
    Grade,
    LeagueStatus,
    SalaryType,
    Specialization,
    UserRole,
)
from django.db import IntegrityError
from django.utils import timezone
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position
from outreach.models import Offer
from profiles.models import CandidateProfile
from rest_framework.test import APIClient


@pytest.fixture
def employer_client(db):
    employer = User.objects.create_user(
        email="emp.r16@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="R16 Inc", contact_email="r16@inc.com")
    CompanyMember.objects.create(company=company, user=employer)
    client = APIClient()
    client.force_authenticate(user=employer)
    return client, employer, company


@pytest.fixture
def candidate_profile(db):
    candidate = User.objects.create_user(
        email="cand.r16@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    profile = CandidateProfile.objects.create(
        user=candidate,
        public_id="C-R16CAND",
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        open_to_offers=True,
    )
    Consent.objects.create(
        user=candidate,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    LeagueMembership.objects.create(
        candidate=candidate,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        base_strength=100.0,
        strength=100.0,
    )
    return candidate, profile


@pytest.mark.django_db
class TestPositionSalaryValidationR16:
    def test_position_create_salary_min_zero_returns_422_salary_invalid(self, employer_client):
        client, _, _ = employer_client
        payload = {
            "title": "Backend Dev",
            "specialization": Specialization.BACKEND,
            "grades": [Grade.MIDDLE],
            "salary_min": 0,
            "salary_max": 200000,
            "salary_type": SalaryType.GROSS,
        }
        res = client.post("/api/positions", payload, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_min" in err_fields

    def test_position_create_salary_max_lt_min_returns_422_salary_invalid(self, employer_client):
        client, _, _ = employer_client
        payload = {
            "title": "Backend Dev",
            "specialization": Specialization.BACKEND,
            "grades": [Grade.MIDDLE],
            "salary_min": 200000,
            "salary_max": 150000,
            "salary_type": SalaryType.GROSS,
        }
        res = client.post("/api/positions", payload, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_max" in err_fields

    def test_position_create_valid_salary_returns_201(self, employer_client):
        client, _, _ = employer_client
        payload = {
            "title": "Backend Dev",
            "specialization": Specialization.BACKEND,
            "grades": [Grade.MIDDLE],
            "salary_min": 150000,
            "salary_max": 200000,
            "salary_type": SalaryType.GROSS,
        }
        res = client.post("/api/positions", payload, format="json")
        assert res.status_code == 201

    def test_position_update_salary_min_zero_returns_422_salary_invalid(self, employer_client):
        client, _, company = employer_client
        pos = Position.objects.create(
            company=company,
            title="Backend Dev",
            specialization=Specialization.BACKEND,
            grades=[Grade.MIDDLE],
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        res = client.put(f"/api/positions/{pos.id}", {"salary_min": 0}, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_min" in err_fields

    def test_position_update_salary_max_lt_min_returns_422_salary_invalid(self, employer_client):
        client, _, company = employer_client
        pos = Position.objects.create(
            company=company,
            title="Backend Dev",
            specialization=Specialization.BACKEND,
            grades=[Grade.MIDDLE],
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        res = client.put(f"/api/positions/{pos.id}", {"salary_max": 80000}, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_max" in err_fields


@pytest.mark.django_db
class TestOfferSalaryValidationR16:
    def test_offer_create_salary_min_zero_returns_422_salary_invalid(
        self, employer_client, candidate_profile
    ):
        client, _, _ = employer_client
        _, profile = candidate_profile

        payload = {
            "candidate_public_id": profile.public_id,
            "title": "Great Offer",
            "salary_min": 0,
            "salary_max": 200000,
            "salary_type": SalaryType.GROSS,
            "contact_channel": ContactChannel.EMAIL,
            "contact_value": "recruiter@r16.com",
        }
        res = client.post("/api/offers", payload, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_min" in err_fields

    def test_offer_create_salary_max_lt_min_returns_422_salary_invalid(
        self, employer_client, candidate_profile
    ):
        client, _, _ = employer_client
        _, profile = candidate_profile

        payload = {
            "candidate_public_id": profile.public_id,
            "title": "Great Offer",
            "salary_min": 200000,
            "salary_max": 100000,
            "salary_type": SalaryType.GROSS,
            "contact_channel": ContactChannel.EMAIL,
            "contact_value": "recruiter@r16.com",
        }
        res = client.post("/api/offers", payload, format="json")
        assert res.status_code == 422
        assert res.data["code"] == "salary_invalid"
        err_fields = [e.get("field") for e in res.data["errors"]]
        assert "salary_max" in err_fields

    def test_offer_create_valid_salary_returns_201(self, employer_client, candidate_profile):
        client, _, _ = employer_client
        _, profile = candidate_profile

        payload = {
            "candidate_public_id": profile.public_id,
            "title": "Great Offer",
            "salary_min": 150000,
            "salary_max": 200000,
            "salary_type": SalaryType.GROSS,
            "contact_channel": ContactChannel.EMAIL,
            "contact_value": "recruiter@r16.com",
        }
        res = client.post("/api/offers", payload, format="json")
        assert res.status_code == 201


@pytest.mark.django_db
class TestSalaryTypeDBConstraintsR16:
    def test_position_invalid_salary_type_violates_db_constraint(self, employer_client):
        _, _, company = employer_client
        with pytest.raises(IntegrityError):
            Position.objects.create(
                company=company,
                title="Invalid Pos",
                specialization=Specialization.BACKEND,
                grades=[Grade.MIDDLE],
                salary_min=100000,
                salary_max=150000,
                salary_type="hourly",  # Not gross or net
            )

    def test_offer_invalid_salary_type_violates_db_constraint(
        self, employer_client, candidate_profile
    ):
        _, employer, company = employer_client
        candidate, _ = candidate_profile
        with pytest.raises(IntegrityError):
            Offer.objects.create(
                company=company,
                candidate=candidate,
                created_by=employer,
                title="Invalid Offer",
                description="Desc",
                salary_min=100000,
                salary_max=150000,
                salary_type="hourly",  # Not gross or net
                contact_channel=ContactChannel.EMAIL,
                contact_value="cand@example.com",
            )
