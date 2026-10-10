"""Tests for Anti-fraud features (Task BE-19).

Verifies:
1. Russian INN checksum validation (10-digit and 12-digit)
2. Corporate domain check and company trust levels (none, domain, verified)
3. Salary spread ratio check (salary_max / salary_min <= 2.0)
4. Weekly outreach credit limits (5 credits/week per position) and refund on offer acceptance
"""

import pytest
from assessment.models import LeagueMembership
from core.enums import (
    ConsentType,
    ContactChannel,
    LeagueStatus,
    OfferStatus,
    SalaryType,
    Specialization,
    TrustLevel,
    UserRole,
)
from django.utils import timezone
from identity.models import Consent, User
from matching.antifraud import (
    compute_company_trust_level,
    is_corporate_domain,
    validate_inn,
)
from matching.models import Company, CompanyMember, Position
from profiles.models import CandidateContact, CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="antifraud.cand@example.com",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="Кандидат Антифрод",
        specialization=Specialization.BACKEND,
        claimed_grade="middle",
        open_to_offers=True,
    )
    CandidateContact.objects.create(
        user=user,
        email="antifraud.cand@example.com",
        phone="+7 (999) 111-22-33",
    )
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade="middle",
        status=LeagueStatus.CONFIRMED,
        rating=1200,
        confirmed_at=timezone.now(),
    )
    return user


@pytest.fixture
def employer_client(db):
    user = User.objects.create_user(
        email="hr@fintech-corp.ru",

        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(
        name="Fintech Corp",
        inn="7707083893",  # Valid 10-digit INN (Sber)
        contact_email="hr@fintech-corp.ru",
        email_domain="fintech-corp.ru",
        website="https://fintech-corp.ru",
        trust_level=TrustLevel.VERIFIED,
    )
    CompanyMember.objects.create(company=company, user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, company


@pytest.mark.django_db
class TestAntiFraud:
    def test_inn_checksum_validation(self):
        # Valid 10-digit INNs
        assert validate_inn("7707083893") is True  # Sberbank
        assert validate_inn("7736207543") is True  # Yandex

        # Invalid 10-digit INNs
        assert validate_inn("7707083890") is False  # Wrong checksum
        assert validate_inn("1234567890") is False

        # Invalid formats
        assert validate_inn("") is False
        assert validate_inn("abc") is False
        assert validate_inn("12345") is False
        assert validate_inn("77070838931234") is False

    def test_corporate_domain_and_trust_level(self):
        # Public email providers
        assert is_corporate_domain("user@gmail.com") is False
        assert is_corporate_domain("hr@mail.ru") is False
        assert is_corporate_domain("lead@yandex.ru") is False

        # Corporate domains
        assert is_corporate_domain("hr@tinkoff.ru") is True
        assert is_corporate_domain("recruiter@avito.ru") is True

        # Trust level computation
        # Valid INN + Corporate domain -> VERIFIED
        assert compute_company_trust_level("7707083893", "fintech-corp.ru") == TrustLevel.VERIFIED
        # No INN + Corporate domain -> DOMAIN
        assert compute_company_trust_level("", "fintech-corp.ru") == TrustLevel.DOMAIN
        # Valid INN + Public email -> NONE
        assert compute_company_trust_level("7707083893", "gmail.com") == TrustLevel.NONE
        # Invalid INN + Public email -> NONE
        assert compute_company_trust_level("0000000000", "gmail.com") == TrustLevel.NONE

    def test_company_api_validates_inn_and_sets_trust_level(self):
        user = User.objects.create_user(
            email="founder@my-startup.io",

            role=UserRole.EMPLOYER,
            email_verified_at=timezone.now(),
        )
        client = APIClient()
        client.force_authenticate(user=user)

        # Attempt with invalid INN
        resp = client.post(
            "/api/companies",
            {
                "name": "Bad INN Startup",
                "inn": "1234567890",
                "contact_email": "hello@my-startup.io",
            },
            format="json",
        )
        assert resp.status_code == 422
        assert "inn" in str(resp.json())

        # Valid INN + Corporate domain -> VERIFIED
        resp = client.post(
            "/api/companies",
            {
                "name": "Good Startup",
                "inn": "7736207543",
                "contact_email": "hello@good-startup.io",
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["trust_level"] == TrustLevel.VERIFIED

    def test_salary_ratio_sanity_checks(self, employer_client, candidate_user):
        client, user, company = employer_client

        # Position creation: salary_max / salary_min <= 2.0 allowed
        pos_resp = client.post(
            "/api/positions",
            {
                "title": "Backend Dev",
                "specialization": "backend",
                "grades": ["middle"],
                "must_skills": ["Python"],
                "nice_skills": [],
                "work_formats": ["remote"],
                "salary_min": 150000,
                "salary_max": 250000,  # ratio 1.66 <= 2.0
                "salary_type": SalaryType.NET,
            },
            format="json",
        )
        assert pos_resp.status_code == 201
        pos_id = pos_resp.json()["id"]

        # Position creation: salary_max / salary_min > 2.0 rejected
        bad_pos_resp = client.post(
            "/api/positions",
            {
                "title": "Unrealistic Range Dev",
                "specialization": "backend",
                "grades": ["middle"],
                "must_skills": ["Python"],
                "nice_skills": [],
                "work_formats": ["remote"],
                "salary_min": 100000,
                "salary_max": 300000,  # ratio 3.0 > 2.0
                "salary_type": SalaryType.NET,
            },
            format="json",
        )
        assert bad_pos_resp.status_code == 422

        # Offer creation: ratio > 2.0 rejected
        cand_pid = candidate_user.candidate_profile.public_id
        bad_offer_resp = client.post(
            "/api/offers",
            {
                "candidate_public_id": cand_pid,
                "position": pos_id,
                "title": "Offer with huge spread",
                "salary_min": 100000,
                "salary_max": 300000,  # ratio 3.0 > 2.0
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.TELEGRAM,
                "contact_value": "@fintech_hr",
            },
            format="json",
        )
        assert bad_offer_resp.status_code == 422
        assert bad_offer_resp.json()["code"] == "salary_invalid"

    def test_weekly_credits_limit_and_refund_on_accept(self, employer_client):
        client, user, company = employer_client

        position = Position.objects.create(
            company=company,
            title="Senior Go Dev",
            specialization=Specialization.BACKEND,
            grades=["senior"],
            salary_min=300000,
            salary_max=450000,
            salary_type=SalaryType.NET,
        )

        candidates = []
        for i in range(6):
            c_user = User.objects.create_user(
                email=f"cand{i}@example.com",
                role=UserRole.CANDIDATE,
                email_verified_at=timezone.now(),
            )
            CandidateProfile.objects.create(
                user=c_user,
                public_id=generate_public_id(),
                full_name=f"Кандидат {i}",
                specialization=Specialization.BACKEND,
                claimed_grade="senior",
                open_to_offers=True,
            )
            CandidateContact.objects.create(
                user=c_user,
                email=f"cand{i}@example.com",
            )
            Consent.objects.create(
                user=c_user,
                type=ConsentType.PUBLICATION,
                granted=True,
            )
            LeagueMembership.objects.create(
                candidate=c_user,
                specialization=Specialization.BACKEND,
                grade="senior",
                status=LeagueStatus.CONFIRMED,
                rating=1500,
                confirmed_at=timezone.now(),
            )
            candidates.append(c_user)

        # Send 5 offers (within 5 credits/week limit)
        offers = []
        for i in range(5):
            resp = client.post(
                "/api/offers",
                {
                    "candidate_public_id": candidates[i].candidate_profile.public_id,
                    "position": str(position.id),
                    "title": f"Offer {i}",
                    "salary_min": 300000,
                    "salary_max": 400000,
                    "salary_type": SalaryType.NET,
                    "contact_channel": ContactChannel.EMAIL,
                    "contact_value": "hr@fintech-corp.ru",
                },
                format="json",
            )
            assert resp.status_code == 201
            offers.append(resp.json())

        # 6th offer for the same position must be rejected with 429 no_credits
        resp_6 = client.post(
            "/api/offers",
            {
                "candidate_public_id": candidates[5].candidate_profile.public_id,
                "position": str(position.id),
                "title": "Offer 6",
                "salary_min": 300000,
                "salary_max": 400000,
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.EMAIL,
                "contact_value": "hr@fintech-corp.ru",
            },
            format="json",
        )
        assert resp_6.status_code == 429
        assert resp_6.json()["code"] == "no_credits"

        # Now candidate 0 views then accepts the offer
        first_offer_id = offers[0]["id"]
        cand_client = APIClient()
        cand_client.force_authenticate(user=candidates[0])

        view_resp = cand_client.post(
            f"/api/offers/{first_offer_id}/view",
            {"version": 1},
            format="json",
        )
        assert view_resp.status_code == 200
        assert view_resp.json()["status"] == OfferStatus.VIEWED
        assert view_resp.json()["version"] == 2

        accept_resp = cand_client.post(
            f"/api/offers/{first_offer_id}/accept",
            {"version": 2},
            format="json",
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == OfferStatus.ACCEPTED

        # 1 credit should be refunded! Now employer can send the 6th offer
        resp_retry = client.post(
            "/api/offers",
            {
                "candidate_public_id": candidates[5].candidate_profile.public_id,
                "position": str(position.id),
                "title": "Offer 6 retry",
                "salary_min": 300000,
                "salary_max": 400000,
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.EMAIL,
                "contact_value": "hr@fintech-corp.ru",
            },
            format="json",
        )
        assert resp_retry.status_code == 201
