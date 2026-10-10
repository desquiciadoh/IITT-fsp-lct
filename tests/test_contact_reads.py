"""Tests for R4: clean contact reads without false denial logs."""

from unittest.mock import patch

import pytest
from core.enums import UserRole
from identity.models import AuditLog, User
from matching.models import Company, CompanyMember, Position
from outreach.models import Offer
from outreach.serializers import OfferSerializer
from outreach.services import ContactAccessService
from profiles.models import CandidateContact, CandidateProfile
from rest_framework.test import APIRequestFactory


@pytest.mark.django_db
class TestContactReads:
    def setup_method(self):
        self.candidate = User.objects.create_user(
            email="cand_r4@example.com",
            password="pass",
            role=UserRole.CANDIDATE,
        )
        self.profile = CandidateProfile.objects.create(
            user=self.candidate,
            full_name="Alice Candidate",
            open_to_offers=True,
            claimed_grade="middle",
            specialization="backend",
        )
        self.contact = CandidateContact.objects.create(
            user=self.candidate,
            email="cand_r4@example.com",
            telegram="@alice",
            phone="+79991234567",
        )
        from assessment.models import LeagueMembership
        from core.enums import Grade, LeagueStatus, Specialization

        LeagueMembership.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
        )

        self.employer = User.objects.create_user(
            email="emp_r4@example.com",
            password="pass",
            role=UserRole.EMPLOYER,
        )
        self.company = Company.objects.create(name="Acme Corp")
        CompanyMember.objects.create(
            company=self.company,
            user=self.employer,
        )

        self.position = Position.objects.create(
            company=self.company,
            title="Backend Dev",
            salary_min=100000,
            salary_max=200000,
            specialization="backend",
            grades=["middle"],
            salary_type="gross",
        )

        self.offer = Offer.objects.create(
            company=self.company,
            candidate=self.candidate,
            position=self.position,
            salary_min=120000,
            salary_max=180000,
            salary_type="gross",
            contact_channel="telegram",
            contact_value="@employer_contact",
        )

    def test_offer_serializer_no_false_denial_audit_logs(self):
        """OfferSerializer.get_candidate_contacts must not create denial AuditLogs when no grant exists."""
        factory = APIRequestFactory()
        request = factory.get("/api/v1/outreach/offers")
        request.user = self.employer

        initial_audit_count = AuditLog.objects.filter(action="contact_access_denied").count()

        serializer = OfferSerializer(self.offer, context={"request": request})
        data = serializer.data

        assert data["candidate_contacts"] is None
        # No denial audit log should have been created just from serializing the offer
        final_audit_count = AuditLog.objects.filter(action="contact_access_denied").count()
        assert final_audit_count == initial_audit_count

    def test_talent_detail_view_catches_only_contact_not_granted(self):
        """TalentDetailView must catch ContactNotGranted specifically, not swallow other Exceptions."""
        from matching.views import TalentDetailView

        factory = APIRequestFactory()
        request = factory.get(f"/api/v1/matching/talent/{self.profile.public_id}")
        request.user = self.employer

        # 1. With normal ContactNotGranted, contacts is None
        # We need publication consent and visibility for TalentDetailView
        from core.enums import ConsentType
        from django.utils import timezone
        from identity.models import Consent

        Consent.objects.create(user=self.candidate, type=ConsentType.PUBLICATION, granted=True)
        self.candidate.email_verified_at = timezone.now()
        self.candidate.save()

        with patch.object(
            ContactAccessService,
            "get_contacts",
            side_effect=RuntimeError("Database connection error"),
        ):
            view = TalentDetailView.as_view()
            with pytest.raises(RuntimeError):
                view(request, public_id=self.profile.public_id)
