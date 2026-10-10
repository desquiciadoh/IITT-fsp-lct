"""Tests for Task BE-20: Candidate controls & Need Health.

Verifies:
1. Candidate contact grant listing and revocation (POST /api/candidates/me/grants/{id}/revoke)
2. Post-revocation contact gating (employer denied with 403 ContactNotGranted)
3. Below-floor private salary warning on offers
4. Acceptance likelihood field calculation (low, medium, high)
5. Need Health decline analytics (GET /api/positions/{id}/health)
"""

import uuid

import pytest
from core.enums import (
    ConsentType,
    ContactChannel,
    ContactGrantSource,
    DeclineReason,
    LeagueStatus,
    OfferStatus,
    SalaryType,
    Specialization,
    TrustLevel,
    UserRole,
    WorkFormat,
)
from core.errors import ContactNotGranted
from django.utils import timezone
from identity.models import AuditLog, Consent, User
from matching.models import Company, CompanyMember, Position
from outreach.models import ContactGrant, Offer
from outreach.services import ContactAccessService
from profiles.models import CandidateContact, CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="ctrl.cand@example.com",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="Иван Контроллеров",
        specialization=Specialization.BACKEND,
        claimed_grade="middle",
        open_to_offers=True,
        salary_min=200000,
        salary_max=250000,
        salary_floor=180000,  # Private floor
        work_formats=[WorkFormat.REMOTE],
    )
    CandidateContact.objects.create(
        user=user,
        email="ctrl.cand@example.com",
        phone="+7 (999) 000-11-22",
        telegram="@ctrl_cand",
    )
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    from assessment.models import LeagueMembership

    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade="middle",
        status=LeagueStatus.CONFIRMED,
        rating=1250,
        confirmed_at=timezone.now(),
    )
    return user


@pytest.fixture
def employer_client(db):
    user = User.objects.create_user(
        email="recruiter@alpha-tech.ru",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(
        name="Alpha Tech",
        inn="7707083893",
        contact_email="recruiter@alpha-tech.ru",
        email_domain="alpha-tech.ru",
        trust_level=TrustLevel.VERIFIED,
    )
    CompanyMember.objects.create(company=company, user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, company


@pytest.mark.django_db
class TestCandidateControlsAndNeedHealth:
    def test_candidate_can_list_and_revoke_contact_grant(self, candidate_user, employer_client):
        _, employer_user, company = employer_client

        # Create active contact grant for company
        grant = ContactGrant.objects.create(
            candidate=candidate_user,
            company=company,
            source=ContactGrantSource.OFFER,
            source_id=uuid.uuid4(),
        )

        cand_client = APIClient()
        cand_client.force_authenticate(user=candidate_user)

        # 1. Candidate lists grants
        resp = cand_client.get("/api/candidates/me/grants")
        assert resp.status_code == 200
        grants_data = resp.json()
        assert len(grants_data) >= 1
        found_grant = next((g for g in grants_data if g["id"] == str(grant.id)), None)
        assert found_grant is not None
        assert found_grant["company"]["name"] == "Alpha Tech"
        assert found_grant["is_active"] is True
        assert found_grant["revoked_at"] is None

        # Employer can access contacts before revocation
        contacts = ContactAccessService.get_contacts(company.id, candidate_user.id, employer_user.id)
        assert contacts.email == "ctrl.cand@example.com"

        # 2. Candidate revokes the grant
        revoke_resp = cand_client.post(f"/api/candidates/me/grants/{grant.id}/revoke")
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["revoked"] is True

        # Grant is now revoked
        grant.refresh_from_db()
        assert grant.is_active is False
        assert grant.revoked_at is not None

        # Employer can NO LONGER read contacts
        with pytest.raises(ContactNotGranted):
            ContactAccessService.get_contacts(company.id, candidate_user.id, employer_user.id)

        # AuditLog recorded revocation
        audit = AuditLog.objects.filter(
            action="contact_grant_revoked",
            target_id=str(grant.id),
        ).first()
        assert audit is not None
        assert audit.actor_id == candidate_user.id

    def test_revocation_forbidden_for_other_candidate(self, candidate_user, employer_client):
        _, _, company = employer_client
        other_user = User.objects.create_user(
            email="other.cand@example.com",
            role=UserRole.CANDIDATE,
            email_verified_at=timezone.now(),
        )
        grant = ContactGrant.objects.create(
            candidate=other_user,
            company=company,
            source=ContactGrantSource.OFFER,
            source_id=uuid.uuid4(),
        )

        cand_client = APIClient()
        cand_client.force_authenticate(user=candidate_user)

        resp = cand_client.post(f"/api/candidates/me/grants/{grant.id}/revoke")
        assert resp.status_code == 404

    def test_below_floor_warning_on_offer_creation(self, candidate_user, employer_client):
        client, _, company = employer_client

        position = Position.objects.create(
            company=company,
            title="Python Developer",
            specialization=Specialization.BACKEND,
            grades=["middle"],
            salary_min=150000,
            salary_max=220000,
            salary_type=SalaryType.NET,
            work_formats=[WorkFormat.REMOTE],
        )

        cand_pid = candidate_user.candidate_profile.public_id

        # Candidate floor is 180,000.
        # Offer A: salary_max = 170,000 (< 180,000) -> triggers below_floor warning
        resp_below = client.post(
            "/api/offers",
            {
                "candidate_public_id": cand_pid,
                "position": str(position.id),
                "title": "Low Offer",
                "salary_min": 120000,
                "salary_max": 170000,
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.TELEGRAM,
                "contact_value": "@alpha_hr",
            },
            format="json",
        )
        assert resp_below.status_code == 201
        data_below = resp_below.json()
        assert data_below["below_floor"] is True
        # Ensure private floor value itself is NOT leaked
        assert "180000" not in str(data_below)

        # Offer B: salary_max = 210,000 (>= 180,000) -> below_floor is False
        resp_ok = client.post(
            "/api/offers",
            {
                "candidate_public_id": cand_pid,
                "position": str(position.id),
                "title": "Fair Offer",
                "salary_min": 180000,
                "salary_max": 210000,
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.TELEGRAM,
                "contact_value": "@alpha_hr",
            },
            format="json",
        )
        assert resp_ok.status_code == 201
        data_ok = resp_ok.json()
        assert data_ok["below_floor"] is False

    def test_acceptance_likelihood_field(self, candidate_user, employer_client):
        client, _, company = employer_client

        position = Position.objects.create(
            company=company,
            title="Backend Engineer",
            specialization=Specialization.BACKEND,
            grades=["middle"],
            salary_min=180000,
            salary_max=230000,
            salary_type=SalaryType.NET,
            work_formats=[WorkFormat.REMOTE],
        )

        cand_pid = candidate_user.candidate_profile.public_id

        # High likelihood offer (matches salary and remote format)
        resp = client.post(
            "/api/offers",
            {
                "candidate_public_id": cand_pid,
                "position": str(position.id),
                "title": "Great Match Offer",
                "salary_min": 190000,
                "salary_max": 240000,
                "salary_type": SalaryType.NET,
                "contact_channel": ContactChannel.TELEGRAM,
                "contact_value": "@alpha_hr",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["acceptance_likelihood"] in ["medium", "high"]

    def test_position_health_analytics(self, candidate_user, employer_client):
        client, employer_user, company = employer_client

        position = Position.objects.create(
            company=company,
            title="Data Platform Engineer",
            specialization=Specialization.BACKEND,
            grades=["middle"],
            salary_min=200000,
            salary_max=300000,
            salary_type=SalaryType.NET,
        )

        # Create multiple offers with various outcomes
        # 1. Accepted offer
        Offer.objects.create(
            company=company,
            candidate=candidate_user,
            created_by=employer_user,
            position=position,
            title="Offer 1",
            salary_min=200000,
            salary_max=250000,
            salary_type=SalaryType.NET,
            contact_channel=ContactChannel.EMAIL,
            contact_value="hr@alpha.ru",
            status=OfferStatus.ACCEPTED,
        )
        # 2. Declined with salary
        Offer.objects.create(
            company=company,
            candidate=candidate_user,
            created_by=employer_user,
            position=position,
            title="Offer 2",
            salary_min=150000,
            salary_max=180000,
            salary_type=SalaryType.NET,
            contact_channel=ContactChannel.EMAIL,
            contact_value="hr@alpha.ru",
            status=OfferStatus.DECLINED,
            decline_reason=DeclineReason.SALARY,
            decline_comment="Мало денег",
        )
        # 3. Declined with salary
        Offer.objects.create(
            company=company,
            candidate=candidate_user,
            created_by=employer_user,
            position=position,
            title="Offer 3",
            salary_min=160000,
            salary_max=190000,
            salary_type=SalaryType.NET,
            contact_channel=ContactChannel.EMAIL,
            contact_value="hr@alpha.ru",
            status=OfferStatus.DECLINED,
            decline_reason=DeclineReason.SALARY,
        )
        # 4. Declined with format
        Offer.objects.create(
            company=company,
            candidate=candidate_user,
            created_by=employer_user,
            position=position,
            title="Offer 4",
            salary_min=200000,
            salary_max=250000,
            salary_type=SalaryType.NET,
            contact_channel=ContactChannel.EMAIL,
            contact_value="hr@alpha.ru",
            status=OfferStatus.DECLINED,
            decline_reason=DeclineReason.FORMAT,
        )
        # 5. Expired
        Offer.objects.create(
            company=company,
            candidate=candidate_user,
            created_by=employer_user,
            position=position,
            title="Offer 5",
            salary_min=200000,
            salary_max=250000,
            salary_type=SalaryType.NET,
            contact_channel=ContactChannel.EMAIL,
            contact_value="hr@alpha.ru",
            status=OfferStatus.EXPIRED,
        )

        # Call GET /api/positions/{id}/health
        resp = client.get(f"/api/positions/{position.id}/health")
        assert resp.status_code == 200
        health = resp.json()

        assert health["total_offers"] == 5
        assert health["accepted_offers"] == 1
        assert health["declined_offers"] == 3
        assert health["expired_offers"] == 1
        assert health["acceptance_rate"] == 0.2
        assert health["decline_rate"] == 0.6

        # Check decline reasons breakdown
        assert health["decline_reasons"]["salary"] == 2
        assert health["decline_reasons"]["format"] == 1
        assert health["top_decline_reason"] == "salary"

        # Health status and diagnosis
        assert health["health_status"] in ["needs_attention", "critical"]
        assert "зарплат" in health["diagnosis"].lower() or "salary" in health["diagnosis"].lower()

        # Credits
        assert "credits_remaining" in health

    def test_position_health_forbidden_for_other_company(self, candidate_user, employer_client):
        client, _, _ = employer_client

        other_company = Company.objects.create(
            name="Other Corp",
            inn="7736207543",
        )
        foreign_position = Position.objects.create(
            company=other_company,
            title="Foreign Dev",
            specialization=Specialization.BACKEND,
            grades=["middle"],
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.NET,
        )

        resp = client.get(f"/api/positions/{foreign_position.id}/health")
        assert resp.status_code in [403, 404]
