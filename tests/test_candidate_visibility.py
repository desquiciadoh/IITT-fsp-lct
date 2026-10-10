"""Tests for R5: Candidate visibility rules and 404 behavior."""

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
from django.utils import timezone
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position
from profiles.models import CandidateProfile, generate_public_id
from profiles.selectors import is_candidate_visible_to_company, visible_candidates_for
from rest_framework.test import APIClient


@pytest.fixture
def visibility_setup(db):
    employer = User.objects.create_user(
        email="emp_vis@example.com",
        password="pass",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="TechCorp")
    CompanyMember.objects.create(company=company, user=employer)
    position = Position.objects.create(
        company=company,
        title="Python Dev",
        specialization=Specialization.BACKEND,
        grades=[Grade.MIDDLE],
        salary_min=100000,
        salary_max=200000,
        salary_type=SalaryType.GROSS,
    )

    candidate = User.objects.create_user(
        email="cand_vis@example.com",
        password="pass",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    profile = CandidateProfile.objects.create(
        user=candidate,
        public_id=generate_public_id(),
        full_name="Alice Developer",
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
        rating=1200,
        confirmed_at=timezone.now(),
    )

    return employer, company, position, candidate, profile


@pytest.mark.django_db
class TestCandidateVisibility:
    def test_visible_candidate_in_selector_and_endpoints(self, visibility_setup):
        employer, company, position, candidate, profile = visibility_setup
        client = APIClient()
        client.force_authenticate(employer)

        # Baseline: visible
        assert is_candidate_visible_to_company(profile, company) is True
        assert visible_candidates_for(company).filter(pk=profile.pk).exists()

        # Check talent detail
        res = client.get(f"/api/talent/{profile.public_id}")
        assert res.status_code == 200

        # Check shortlist PUT
        res = client.put(f"/api/positions/{position.id}/shortlist/{profile.public_id}")
        assert res.status_code == 204

    def test_revoked_consent_hides_candidate_everywhere(self, visibility_setup):
        employer, company, position, candidate, profile = visibility_setup
        client = APIClient()
        client.force_authenticate(employer)

        # Revoke publication consent
        Consent.objects.create(
            user=candidate,
            type=ConsentType.PUBLICATION,
            granted=False,
        )

        # 1. Selector check
        assert is_candidate_visible_to_company(profile, company) is False
        assert not visible_candidates_for(company).filter(pk=profile.pk).exists()

        # 2. Talent card -> 404
        res = client.get(f"/api/talent/{profile.public_id}")
        assert res.status_code == 404

        # 3. Talent search -> not present
        res = client.get("/api/talent/search")
        assert res.status_code == 200
        found_ids = [item["public_id"] for item in res.data.get("items", [])]
        assert profile.public_id not in found_ids

        # 4. Position pool -> not present
        res = client.get(f"/api/positions/{position.id}/pool")
        assert res.status_code == 200
        found_ids = [item["public_id"] for item in res.data.get("items", [])]
        assert profile.public_id not in found_ids

        # 5. Shortlist PUT -> 404
        res = client.put(f"/api/positions/{position.id}/shortlist/{profile.public_id}")
        assert res.status_code == 404

        # 6. Offer POST -> 404
        res = client.post(
            "/api/offers",
            {
                "candidate_public_id": profile.public_id,
                "title": "Job Offer",
                "salary_min": 120000,
                "salary_max": 180000,
                "salary_type": SalaryType.GROSS,
                "contact_channel": ContactChannel.EMAIL,
                "contact_value": "hr@techcorp.com",
            },
            format="json",
        )
        assert res.status_code == 404

    def test_shortlist_and_offer_return_identical_404_for_invisible_and_nonexistent(
        self, visibility_setup
    ):
        employer, company, position, candidate, profile = visibility_setup
        client = APIClient()
        client.force_authenticate(employer)

        # Block company to make candidate invisible
        profile.blocked_company_ids = [company.id]
        profile.save()

        # Invisible candidate
        inv_shortlist_res = client.put(
            f"/api/positions/{position.id}/shortlist/{profile.public_id}"
        )
        inv_offer_res = client.post(
            "/api/offers",
            {
                "candidate_public_id": profile.public_id,
                "title": "Job Offer",
                "salary_min": 120000,
                "salary_max": 180000,
                "salary_type": SalaryType.GROSS,
                "contact_channel": ContactChannel.EMAIL,
                "contact_value": "hr@techcorp.com",
            },
            format="json",
        )

        # Nonexistent candidate
        non_shortlist_res = client.put(f"/api/positions/{position.id}/shortlist/C-NONEXIST")
        non_offer_res = client.post(
            "/api/offers",
            {
                "candidate_public_id": "C-NONEXIST",
                "title": "Job Offer",
                "salary_min": 120000,
                "salary_max": 180000,
                "salary_type": SalaryType.GROSS,
                "contact_channel": ContactChannel.EMAIL,
                "contact_value": "hr@techcorp.com",
            },
            format="json",
        )

        # Both must return 404
        assert inv_shortlist_res.status_code == 404
        assert non_shortlist_res.status_code == 404
        assert inv_shortlist_res.data == non_shortlist_res.data

        assert inv_offer_res.status_code == 404
        assert non_offer_res.status_code == 404
        assert inv_offer_res.data == non_offer_res.data

    def test_pending_only_league_is_invisible(self, visibility_setup):
        employer, company, position, candidate, profile = visibility_setup
        # Set all leagues to PENDING
        LeagueMembership.objects.filter(candidate=candidate).update(status=LeagueStatus.PENDING)

        assert is_candidate_visible_to_company(profile, company) is False
        assert not visible_candidates_for(company).filter(pk=profile.pk).exists()

    def test_unverified_email_is_invisible(self, visibility_setup):
        employer, company, position, candidate, profile = visibility_setup
        candidate.email_verified_at = None
        candidate.save()

        assert is_candidate_visible_to_company(profile, company) is False
        assert not visible_candidates_for(company).filter(pk=profile.pk).exists()

    def test_not_open_to_offers_is_invisible(self, visibility_setup):
        employer, company, position, candidate, profile = visibility_setup
        profile.open_to_offers = False
        profile.save()

        assert is_candidate_visible_to_company(profile, company) is False
        assert not visible_candidates_for(company).filter(pk=profile.pk).exists()
