"""Test Contact Gating (0 Leaks Invariant).

INVARIANT: Candidate contacts (email, phone, telegram) are STRICTLY hidden
from employers until the candidate explicitly accepts a Draft Offer.
Any access attempt without an active ContactGrant must raise ContactNotGranted
and be recorded in AuditLog.
"""
import pytest
from core.enums import OfferStatus, SalaryType, UserRole
from core.errors import ContactNotGranted
from django.utils import timezone
from identity.models import AuditLog, User
from matching.models import Company, CompanyMember
from outreach.models import ContactGrant, Offer
from outreach.services import ContactAccessService, OfferService
from profiles.models import CandidateContact, CandidateProfile, generate_public_id


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email='secret.candidate@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name='Секретный Кандидат',
        open_to_offers=True,
    )
    CandidateContact.objects.create(
        user=user,
        email='secret.candidate@example.com',
        phone='+7 (999) 000-00-00',
        telegram='@secret_dev',
    )
    return user


@pytest.fixture
def employer_company(db):
    company = Company.objects.create(
        name='Tech Corp',
        contact_email='hr@techcorp.com',
    )
    employer_user = User.objects.create_user(
        email='recruiter@techcorp.com',
        password='password123',
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    CompanyMember.objects.create(company=company, user=employer_user)
    return company, employer_user


@pytest.mark.django_db
class TestContactGating:

    def test_no_contacts_without_offer(self, candidate, employer_company):
        """Employer cannot read contacts when no offer exists."""
        company, employer_user = employer_company

        with pytest.raises(ContactNotGranted):
            ContactAccessService.get_contacts(
                company_id=company.id,
                candidate_id=candidate.id,
                actor_id=employer_user.id,
            )

        # Verify denied access is logged in AuditLog
        audit = AuditLog.objects.filter(
            actor_id=employer_user.id,
            action='contact_access_denied',
            target_id=str(candidate.id),
        ).first()
        assert audit is not None, "Failed contact access must be logged in AuditLog!"

    def test_no_contacts_when_offer_is_sent(self, candidate, employer_company):
        """Contacts remain strictly gated when offer status is SENT."""
        company, employer_user = employer_company
        Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer_user,
            title='Junior Backend',
            description='Offer details',
            salary_min=150000,
            salary_max=200000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@techcorp.com',
            status=OfferStatus.SENT,
        )

        with pytest.raises(ContactNotGranted):
            ContactAccessService.get_contacts(
                company_id=company.id,
                candidate_id=candidate.id,
                actor_id=employer_user.id,
            )

    def test_no_contacts_when_offer_is_viewed(self, candidate, employer_company):
        """Contacts remain strictly gated when candidate views offer."""
        company, employer_user = employer_company
        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer_user,
            title='Junior Backend',
            description='Offer details',
            salary_min=150000,
            salary_max=200000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@techcorp.com',
            status=OfferStatus.SENT,
        )

        OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=offer.version,
            actor_id=candidate.id,
        )

        with pytest.raises(ContactNotGranted):
            ContactAccessService.get_contacts(
                company_id=company.id,
                candidate_id=candidate.id,
                actor_id=employer_user.id,
            )

    def test_contacts_unlocked_on_accepted_offer(self, candidate, employer_company):
        """Contacts become accessible ONLY after offer is ACCEPTED."""
        company, employer_user = employer_company
        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer_user,
            title='Junior Backend',
            description='Offer details',
            salary_min=150000,
            salary_max=200000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@techcorp.com',
            status=OfferStatus.SENT,
        )

        # Transition: SENT -> VIEWED -> ACCEPTED
        offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=offer.version,
            actor_id=candidate.id,
        )
        offer = OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.ACCEPTED,
            expected_version=offer.version,
            actor_id=candidate.id,
        )

        # ContactGrant must have been automatically created
        grant = ContactGrant.objects.filter(company=company, candidate=candidate).first()
        assert grant is not None
        assert grant.is_active

        # Now contacts can be safely read
        contacts = ContactAccessService.get_contacts(
            company_id=company.id,
            candidate_id=candidate.id,
            actor_id=employer_user.id,
        )
        assert contacts.email == 'secret.candidate@example.com'
        assert contacts.phone == '+7 (999) 000-00-00'
        assert contacts.telegram == '@secret_dev'

        # Verify access granted is logged in AuditLog
        assert AuditLog.objects.filter(
            actor_id=employer_user.id,
            action='contact_access_granted',
            target_id=str(candidate.id),
        ).exists()

    def test_no_contacts_when_offer_declined(self, candidate, employer_company):
        """Declined offer does not grant contacts."""
        company, employer_user = employer_company
        offer = Offer.objects.create(
            company=company,
            candidate=candidate,
            created_by=employer_user,
            title='Junior Backend',
            description='Offer details',
            salary_min=150000,
            salary_max=200000,
            salary_type=SalaryType.GROSS,
            contact_channel='email',
            contact_value='hr@techcorp.com',
            status=OfferStatus.SENT,
        )

        OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.VIEWED,
            expected_version=offer.version,
            actor_id=candidate.id,
        )
        OfferService.transition(
            offer_id=offer.id,
            new_status=OfferStatus.DECLINED,
            expected_version=offer.version + 1,
            actor_id=candidate.id,
            decline_reason='salary',
        )

        with pytest.raises(ContactNotGranted):
            ContactAccessService.get_contacts(
                company_id=company.id,
                candidate_id=candidate.id,
                actor_id=employer_user.id,
            )
