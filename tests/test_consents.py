import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.enums import ConsentType, OfferStatus, SalaryType, UserRole
from identity.models import Consent, User
from matching.models import Company, CompanyMember
from outreach.models import Offer
from profiles.models import CandidateProfile, generate_public_id
from profiles.selectors import visible_candidates_for


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email='consent.candidate@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name='Consent Candidate',
        open_to_offers=True,
    )
    Consent.objects.create(
        user=user,
        type=ConsentType.PROCESSING,
        granted=True,
    )
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    return user


@pytest.fixture
def employer_with_company(db):
    employer = User.objects.create_user(
        email='consent.employer@example.com',
        password='password123',
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(
        name='Consent Company',
        contact_email='hr@consent.com',
    )
    CompanyMember.objects.create(company=company, user=employer)
    return employer, company


@pytest.mark.django_db
def test_consents_get_and_put(candidate_user):
    client = APIClient()
    client.force_authenticate(candidate_user)

    # GET consents
    res = client.get('/api/candidates/me/consents')
    assert res.status_code == 200
    assert res.data['publication'] is True
    assert res.data['processing'] is True

    # PUT consents with boolean
    res = client.put('/api/candidates/me/consents', {'fsp_sync': True}, format='json')
    assert res.status_code == 200
    assert res.data['fsp_sync'] is True

    # PUT consents with string "false" - must parse to False (B20)
    res = client.put('/api/candidates/me/consents', {'fsp_sync': 'false'}, format='json')
    assert res.status_code == 200
    assert res.data['fsp_sync'] is False


@pytest.mark.django_db
def test_employer_cannot_manage_consents(employer_with_company):
    employer, _ = employer_with_company
    client = APIClient()
    client.force_authenticate(employer)

    res = client.put('/api/candidates/me/consents', {'publication': True}, format='json')
    assert res.status_code == 403


@pytest.mark.django_db
def test_publication_consent_revocation_withdraws_pending_offers(candidate_user, employer_with_company):
    employer, company = employer_with_company
    
    # Create a pending offer (SENT)
    offer_sent = Offer.objects.create(
        company=company,
        candidate=candidate_user,
        created_by=employer,
        title='Backend Dev',
        description='Work with us',
        salary_min=150000,
        salary_max=200000,
        salary_type=SalaryType.GROSS,
        contact_channel='email',
        contact_value='hr@consent.com',
        status=OfferStatus.SENT,
    )
    # Create an offer in VIEWED status
    offer_viewed = Offer.objects.create(
        company=company,
        candidate=candidate_user,
        created_by=employer,
        title='Senior Dev',
        description='Senior role',
        salary_min=250000,
        salary_max=300000,
        salary_type=SalaryType.GROSS,
        contact_channel='email',
        contact_value='hr@consent.com',
        status=OfferStatus.VIEWED,
    )

    client = APIClient()
    client.force_authenticate(candidate_user)

    # Revoke publication consent
    res = client.put('/api/candidates/me/consents', {'publication': False}, format='json')
    assert res.status_code == 200
    assert res.data['publication'] is False

    offer_sent.refresh_from_db()
    offer_viewed.refresh_from_db()
    assert offer_sent.status == OfferStatus.WITHDRAWN
    assert offer_viewed.status == OfferStatus.WITHDRAWN


@pytest.mark.django_db
def test_publication_consent_revocation_hides_from_pool(candidate_user, employer_with_company):
    _, company = employer_with_company
    # Candidate currently visible
    visible = visible_candidates_for(company)
    assert any(c.user_id == candidate_user.id for c in visible)

    client = APIClient()
    client.force_authenticate(candidate_user)

    # Revoke publication consent
    res = client.put('/api/candidates/me/consents', {'publication': False}, format='json')
    assert res.status_code == 200

    # Candidate should no longer be visible
    visible_after = visible_candidates_for(company)
    assert not any(c.user_id == candidate_user.id for c in visible_after)
