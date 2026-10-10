"""Tests for R8: No internal UUIDs in employer-facing payloads."""

import uuid

import pytest
from assessment.models import AssessmentSession, LeagueMembership
from core.enums import (
    AssessmentKind,
    AssessmentMode,
    AssessmentStatus,
    Grade,
    LeagueStatus,
    Specialization,
    UserRole,
)
from identity.models import Consent, User
from matching.models import Company, CompanyMember
from outreach.events import publish_domain_event
from profiles.models import CandidateProfile
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestEmployerPayloadPrivacy:
    def setup_method(self):
        self.candidate = User.objects.create_user(
            email="cand_r8@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        self.candidate.email_verified_at = "2025-01-01T00:00:00Z"
        self.candidate.save()

        Consent.objects.create(
            user=self.candidate,
            type="publication",
            granted=True,
            version=1,
        )

        self.profile = CandidateProfile.objects.create(
            user=self.candidate,
            full_name="Boris Talent",
            open_to_offers=True,
            claimed_grade=Grade.MIDDLE,
            specialization=Specialization.BACKEND,
            blind_mode=False,
        )

        self.league = LeagueMembership.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
        )

        self.session = AssessmentSession.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            kind=AssessmentKind.INITIAL,
            mode=AssessmentMode.FULL,
            status=AssessmentStatus.FINISHED,
            result_grade=Grade.MIDDLE,
            rating=1100,
        )

        self.employer = User.objects.create_user(
            email="emp_r8@example.com",
            password="password123",
            role=UserRole.EMPLOYER,
        )
        self.company = Company.objects.create(name="CyberTech")
        CompanyMember.objects.create(
            company=self.company,
            user=self.employer,
        )

        self.client = APIClient()

    def test_talent_detail_assessments_id_is_public_id_not_uuid(self):
        """Employer viewing talent card must see public assessment IDs, not internal UUID."""
        self.client.force_authenticate(user=self.employer)
        res = self.client.get(f"/api/talent/{self.profile.public_id}")
        assert res.status_code == 200
        data = res.json()

        assert len(data["assessments"]) >= 1
        assessment_entry = data["assessments"][0]
        # Must not be the internal UUID
        assert assessment_entry["id"] != str(self.session.id)
        # Must start with public ID format (e.g. A-)
        assert assessment_entry["id"].startswith("A-")
        # Check property on model
        assert hasattr(self.session, "public_id")
        assert assessment_entry["id"] == self.session.public_id

    def test_non_blind_display_name_shows_full_name(self):
        """Non-blind profile shows full_name, blind mode shows alias."""
        self.client.force_authenticate(user=self.employer)
        res = self.client.get(f"/api/talent/{self.profile.public_id}")
        assert res.status_code == 200
        assert res.json()["display_name"] == "Boris Talent"

        self.profile.blind_mode = True
        self.profile.save()

        res_blind = self.client.get(f"/api/talent/{self.profile.public_id}")
        assert res_blind.status_code == 200
        assert res_blind.json()["display_name"] == f"Кандидат {self.profile.public_id}"

    def test_sse_employer_receives_candidate_public_id(self, django_capture_on_commit_callbacks):
        """In SSE streams for employers, candidate_id in payloads is transformed to public_id."""
        self.client.force_authenticate(user=self.employer)

        # Publish an event with internal user UUID
        with django_capture_on_commit_callbacks(execute=True):
            publish_domain_event(
                "offer.created",
                {
                    "offer_id": str(uuid.uuid4()),
                    "candidate_id": str(self.candidate.id),
                    "company_id": str(self.company.id),
                    "title": "Test Offer",
                    "status": "sent",
                },
            )

        # Connect with limit=1 to read the event
        res = self.client.get("/api/events?limit=1")
        assert res.status_code == 200
        content = b"".join(res.streaming_content).decode("utf-8")

        # The internal UUID must not be present as candidate_id
        assert f'"candidate_id": "{self.candidate.id}"' not in content
        # The public_id must be present as candidate_id
        assert f'"candidate_id": "{self.profile.public_id}"' in content
