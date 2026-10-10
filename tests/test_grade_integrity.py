"""Tests for R9 and R10: Grade integrity, promotion failure handling, and verify endpoint."""

import pytest
from assessment.models import AssessmentItem, AssessmentSession, ItemFamily, LeagueMembership
from assessment.services import AssessmentService
from core.enums import (
    AssessmentKind,
    AssessmentMode,
    AssessmentStatus,
    Grade,
    GradeDecision,
    ItemFamilyStatus,
    ItemFormat,
    LeagueStatus,
    Specialization,
    UserRole,
)
from identity.models import Consent, User
from matching.models import Company, CompanyMember
from profiles.models import CandidateProfile
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestGradeIntegrity:
    def setup_method(self):
        self.candidate = User.objects.create_user(
            email="integrity_cand@example.com",
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
            full_name="Integrity Candidate",
            open_to_offers=True,
            claimed_grade=Grade.MIDDLE,
            specialization=Specialization.BACKEND,
        )

        # Existing CONFIRMED Middle league
        self.membership = LeagueMembership.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
            theta=0.5,
            rating=1100,
            strength=60.0,
            base_strength=60.0,
            confirmed_at="2025-01-01T12:00:00Z",
        )

        # Family for items
        self.family, _ = ItemFamily.objects.get_or_create(
            id="fam_integ_test",
            defaults={
                "version": 1,
                "specs": [Specialization.BACKEND],
                "topic": "Python",
                "format": ItemFormat.CONCEPT_MCQ,
                "a": 1.0,
                "b": 1.5,
                "c": 0.25,
                "status": ItemFamilyStatus.ACTIVE,
            },
        )

        self.employer = User.objects.create_user(
            email="integrity_emp@example.com",
            password="password123",
            role=UserRole.EMPLOYER,
        )
        self.company = Company.objects.create(name="Integrity Co")
        CompanyMember.objects.create(user=self.employer, company=self.company)
        self.client = APIClient()

    def test_failed_higher_claim_preserves_confirmed_grade_and_status(self):
        """If league is CONFIRMED at grade G, a failed higher claim keeps G and CONFIRMED."""
        # Create an in-progress session claiming SENIOR (promotion)
        session = AssessmentSession.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.SENIOR,
            kind=AssessmentKind.PROMOTION,
            mode=AssessmentMode.FULL,
            status=AssessmentStatus.IN_PROGRESS,
        )
        # Add an answered item with incorrect answer
        AssessmentItem.objects.create(
            assessment=session,
            seq=1,
            family=self.family,
            seed=42,
            view={"q": "test"},
            key={"val": "correct"},
            fingerprint="fp1",
            correct=False,
            answered_at="2025-01-02T12:00:00Z",
        )

        # Finalize the assessment (unconfirmed because incorrect / below senior)
        AssessmentService.finalize_assessment(session, self.candidate, timed_out=False)

        session.refresh_from_db()
        self.membership.refresh_from_db()

        # Session records unconfirmed attempt
        assert session.decision == GradeDecision.UNCONFIRMED
        assert session.status == AssessmentStatus.FINISHED
        # R10: session stores scorer's achieved grade, not claimed_grade
        assert session.result_grade != Grade.SENIOR

        # League membership must PRESERVE confirmed Middle grade
        assert self.membership.grade == Grade.MIDDLE
        assert self.membership.status == LeagueStatus.CONFIRMED
        assert self.membership.confirmed_at is not None
        assert self.membership.next_attempt_at is not None

    def test_abandoned_promotion_preserves_confirmed_grade(self):
        """Abandoning a promotion assessment does not wipe confirmed grade."""
        session = AssessmentSession.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.SENIOR,
            kind=AssessmentKind.PROMOTION,
            mode=AssessmentMode.FULL,
            status=AssessmentStatus.IN_PROGRESS,
        )
        AssessmentItem.objects.create(
            assessment=session,
            seq=1,
            family=self.family,
            seed=42,
            view={"q": "test"},
            key={"val": "correct"},
            fingerprint="fp1",
        )

        AssessmentService.abandon_assessment(self.candidate, session.id)

        self.membership.refresh_from_db()
        assert self.membership.grade == Grade.MIDDLE
        assert self.membership.status == LeagueStatus.CONFIRMED
        assert self.membership.confirmed_at is not None

    def test_unconfirmed_status_clears_confirmed_at(self):
        """Whenever league status becomes UNCONFIRMED, confirmed_at must be cleared (None)."""
        # User without previous confirmed grade
        new_cand = User.objects.create_user(
            email="new_cand@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        session = AssessmentSession.objects.create(
            candidate=new_cand,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            kind=AssessmentKind.INITIAL,
            mode=AssessmentMode.FULL,
            status=AssessmentStatus.IN_PROGRESS,
        )
        AssessmentItem.objects.create(
            assessment=session,
            seq=1,
            family=self.family,
            seed=42,
            view={"q": "test"},
            key={"val": "correct"},
            fingerprint="fp2",
            correct=False,
            answered_at="2025-01-02T12:00:00Z",
        )

        AssessmentService.finalize_assessment(session, new_cand, timed_out=True)

        mem = LeagueMembership.objects.filter(
            candidate=new_cand, specialization=Specialization.BACKEND
        ).first()
        assert mem is not None
        assert mem.status == LeagueStatus.UNCONFIRMED
        assert mem.confirmed_at is None

    def test_verify_never_returns_valid_true_for_unconfirmed(self):
        """/api/verify/<public_id> never returns valid: true when status is UNCONFIRMED."""
        # Force membership to unconfirmed with lingering confirmed_at
        self.membership.status = LeagueStatus.UNCONFIRMED
        self.membership.save()

        res = self.client.get(f"/api/verify/{self.profile.public_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False

    def test_talent_detail_shows_decision_next_to_result_grade(self):
        """Talent card assessments list includes 'decision' field."""
        session = AssessmentSession.objects.create(
            candidate=self.candidate,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.SENIOR,
            kind=AssessmentKind.PROMOTION,
            mode=AssessmentMode.FULL,
            status=AssessmentStatus.FINISHED,
            result_grade=Grade.MIDDLE,
            decision=GradeDecision.UNCONFIRMED,
            rating=1050,
            finished_at="2025-01-02T12:00:00Z",
        )

        self.client.force_authenticate(user=self.employer)
        res = self.client.get(f"/api/talent/{self.profile.public_id}")
        assert res.status_code == 200
        card = res.json()

        matching_assessments = [a for a in card["assessments"] if a["id"] == session.public_id]
        assert len(matching_assessments) == 1
        ass_card = matching_assessments[0]
        assert ass_card["result_grade"] == Grade.MIDDLE
        assert ass_card["decision"] == GradeDecision.UNCONFIRMED
