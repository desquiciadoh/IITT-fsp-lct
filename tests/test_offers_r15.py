"""Tests for Task R15 (Offers lifecycle, consent revoke, and cooldown retry-after)."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from core.enums import ConsentType, OfferStatus, SalaryType, UserRole
from core.errors import CooldownActive, InvalidTransition
from django.utils import timezone
from identity.models import AuditLog, User
from matching.models import Company, CompanyMember
from outreach.models import Offer
from outreach.services import OfferService
from rest_framework.test import APIClient
from rest_framework.views import APIView


@pytest.fixture
def candidate_and_company(db):
    candidate = User.objects.create_user(
        email="cand.r15@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="R15 Corp", contact_email="r15@corp.com")
    employer = User.objects.create_user(
        email="emp.r15@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    CompanyMember.objects.create(company=company, user=employer)
    return candidate, company, employer


@pytest.mark.django_db
class TestExpireOffersR15:
    def test_expire_offers_reuses_expire_locked_and_creates_audit_log(self, candidate_and_company):
        candidate, company, employer = candidate_and_company
        now = timezone.now()

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title="Stale Offer",
            description="...",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
            contact_channel="email",
            contact_value="cand@example.com",
            status=OfferStatus.SENT,
            version=1,
            expires_at=now - timedelta(hours=1),
        )

        count = OfferService.expire_offers()
        assert count == 1

        offer.refresh_from_db()
        assert offer.status == OfferStatus.EXPIRED

        # Verify AuditLog created by _expire_locked
        audit = AuditLog.objects.filter(
            action="offer_expired",
            target_type="Offer",
            target_id=str(offer.id),
        ).first()
        assert audit is not None
        assert audit.meta.get("new_status") == OfferStatus.EXPIRED

    def test_expire_offers_isolates_per_row_failures(self, candidate_and_company):
        candidate, company, employer = candidate_and_company
        now = timezone.now()

        offer1 = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title="Offer 1",
            description="...",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
            contact_channel="email",
            contact_value="cand@example.com",
            status=OfferStatus.SENT,
            version=1,
            expires_at=now - timedelta(hours=2),
        )
        offer2 = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title="Offer 2",
            description="...",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
            contact_channel="email",
            contact_value="cand@example.com",
            status=OfferStatus.SENT,
            version=1,
            expires_at=now - timedelta(hours=1),
        )

        original_expire_locked = OfferService._expire_locked

        def flawed_expire_locked(locked_offer, actor_id, ts):
            if locked_offer.id == offer1.id:
                raise RuntimeError("Simulated DB lock failure on offer1")
            return original_expire_locked(locked_offer, actor_id, ts)

        with patch.object(OfferService, "_expire_locked", side_effect=flawed_expire_locked):
            count = OfferService.expire_offers()

        assert count == 1
        offer1.refresh_from_db()
        offer2.refresh_from_db()
        assert offer1.status == OfferStatus.SENT
        assert offer2.status == OfferStatus.EXPIRED


@pytest.mark.django_db
class TestConsentRevokeR15:
    def test_consent_revoke_retries_version_conflict(self, candidate_and_company):
        candidate, company, employer = candidate_and_company
        client = APIClient()
        client.force_authenticate(user=candidate)

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title="Pending Offer",
            description="...",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
            contact_channel="email",
            contact_value="cand@example.com",
            status=OfferStatus.SENT,
            version=1,
        )

        # Simulate concurrent version bump before revocation tries to withdraw
        offer.version = 2
        offer.save(update_fields=["version"])

        res = client.put(
            "/api/candidates/me/consents",
            {
                ConsentType.PUBLICATION: False,
            },
            format="json",
        )

        assert res.status_code == 200
        offer.refresh_from_db()
        assert offer.status == OfferStatus.WITHDRAWN

    def test_consent_revoke_handles_expired_or_invalid_transition(self, candidate_and_company):
        candidate, company, employer = candidate_and_company
        client = APIClient()
        client.force_authenticate(user=candidate)

        # Create offer in accepted state (cannot be withdrawn)
        Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title="Accepted Offer",
            description="...",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
            contact_channel="email",
            contact_value="cand@example.com",
            status=OfferStatus.ACCEPTED,
            version=1,
        )

        with patch.object(
            OfferService,
            "transition",
            side_effect=InvalidTransition(OfferStatus.ACCEPTED, OfferStatus.WITHDRAWN),
        ):
            res = client.put(
                "/api/candidates/me/consents",
                {
                    ConsentType.PUBLICATION: False,
                },
                format="json",
            )

        assert res.status_code == 200


@pytest.mark.django_db
class TestCooldownActiveRetryAfterR15:
    def test_cooldown_active_sends_retry_after_header(self):
        class DummyCooldownView(APIView):
            def get(self, request):
                next_at = timezone.now() + timedelta(seconds=120)
                raise CooldownActive(next_at.isoformat())

        # Call an endpoint that raises CooldownActive
        from core.errors import fsp_exception_handler
        from django.test import RequestFactory
        from rest_framework.request import Request

        next_time = timezone.now() + timedelta(seconds=120)
        exc = CooldownActive(next_time.isoformat())
        rf = RequestFactory()
        req = rf.get("/dummy")
        response = fsp_exception_handler(exc, {"request": Request(req)})

        assert response.status_code == 429
        assert "Retry-After" in response
        retry_after = int(response["Retry-After"])
        assert 115 <= retry_after <= 125
