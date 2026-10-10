"""Test Offer State Machine and Optimistic Locking (Version Conflict).

INVARIANTS:
1. Valid transitions: sent -> viewed -> accepted / declined / withdrawn
2. Invalid transitions must raise InvalidTransition (409)
3. Optimistic locking: concurrent update with old version raises VersionConflict (409)
4. Salary constraints: salary_min > 0 and salary_max >= salary_min
"""
import pytest
from core.enums import OfferStatus, SalaryType, UserRole
from core.errors import InvalidTransition, VersionConflict
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember
from outreach.models import Offer
from outreach.services import OfferService


@pytest.fixture
def test_setup(db):
    candidate = User.objects.create_user(
        email='cand.offers@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name='Test Company', contact_email='info@test.com')
    employer = User.objects.create_user(
        email='emp.offers@example.com',
        password='password123',
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    CompanyMember.objects.create(company=company, user=employer)
    return candidate, company, employer


@pytest.mark.django_db
class TestOfferStateMachine:

    def test_valid_lifecycle_transitions(self, test_setup):
        """Test full happy path: SENT -> VIEWED -> ACCEPTED."""
        candidate, company, employer = test_setup

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title='Python Lead',
            description='Role details',
            salary_min=200000,
            salary_max=300000,
            salary_type=SalaryType.NET,
            contact_channel='telegram',
            contact_value='@hr_lead',
            status=OfferStatus.SENT,
            version=1,
        )

        # 1. Candidate views offer: SENT -> VIEWED (version becomes 2)
        offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=1,
            actor_id=candidate.id,
        )
        assert offer.status == OfferStatus.VIEWED
        assert offer.version == 2

        # 2. Candidate accepts offer: VIEWED -> ACCEPTED (version becomes 3)
        offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.ACCEPTED,
            expected_version=2,
            actor_id=candidate.id,
        )
        assert offer.status == OfferStatus.ACCEPTED
        assert offer.version == 3

    def test_invalid_transition_raises_error(self, test_setup):
        """Cannot accept offer directly from SENT without VIEWED."""
        candidate, company, employer = test_setup

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title='Backend Dev',
            description='...',
            salary_min=180000,
            salary_max=220000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@company.com',
            status=OfferStatus.SENT,
            version=1,
        )

        with pytest.raises(InvalidTransition):
            OfferService.transition(
                offer_id=offer.id,
                new_status=OfferStatus.ACCEPTED,
                expected_version=1,
                actor_id=candidate.id,
            )

    def test_terminal_state_cannot_transition(self, test_setup):
        """Declined offer cannot transition to any other status."""
        candidate, company, employer = test_setup

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title='Backend Dev',
            description='...',
            salary_min=180000,
            salary_max=220000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@company.com',
            status=OfferStatus.DECLINED,
            version=1,
        )

        with pytest.raises(InvalidTransition):
            OfferService.transition(
                offer_id=offer.id,
                new_status=OfferStatus.ACCEPTED,
                expected_version=1,
                actor_id=candidate.id,
            )

    def test_version_conflict_optimistic_locking(self, test_setup):
        """Concurrent requests with stale version must raise VersionConflict (409)."""
        candidate, company, employer = test_setup

        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer,
            title='ML Engineer',
            description='...',
            salary_min=250000,
            salary_max=350000,
            salary_type=SalaryType.NET,
            contact_channel='email',
            contact_value='hr@company.com',
            status=OfferStatus.SENT,
            version=1,
        )

        # First request succeeds (SENT -> VIEWED, version 1 -> 2)
        OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=1,
            actor_id=candidate.id,
        )

        # Concurrent request trying with stale version=1 must fail with VersionConflict!
        with pytest.raises(VersionConflict):
            OfferService.transition(
                offer_id=offer.id,
                new_status=OfferStatus.WITHDRAWN,
                expected_version=1,  # Stale version!
                actor_id=employer.id,
            )

    def test_salary_constraints(self, test_setup):
        """DB CheckConstraints enforce salary_min > 0 and salary_max >= salary_min."""
        from django.db import transaction
        candidate, company, employer = test_setup

        # Invalid: salary_min = 0 (violates salary_min > 0)
        with transaction.atomic():
            with pytest.raises((IntegrityError, ValidationError)):
                Offer.objects.create(
                    company=company,
                    candidate=candidate,
                    created_by=employer,
                    title='Invalid Salary Offer',
                    description='...',
                    salary_min=0,
                    salary_max=100000,
                    salary_type=SalaryType.GROSS,
                    contact_channel='email',
                    contact_value='hr@company.com',
                )

        # Invalid: salary_max < salary_min (violates salary_max >= salary_min)
        with transaction.atomic():
            with pytest.raises((IntegrityError, ValidationError)):
                Offer.objects.create(
                    company=company,
                    candidate=candidate,
                    created_by=employer,
                    title='Invalid Salary Range Offer',
                    description='...',
                    salary_min=200000,
                    salary_max=150000,
                    salary_type=SalaryType.GROSS,
                    contact_channel='email',
                    contact_value='hr@company.com',
                )
