import uuid
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.enums import ConsentType, Grade, LeagueStatus, Specialization, UserRole
from assessment.models import LeagueMembership
from identity.models import Consent, User
from matching.models import Company
from profiles.models import CandidateProfile, generate_public_id


@pytest.fixture
def candidate_without_profile(db):
    user = User.objects.create_user(
        email='noprofile@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    return user


@pytest.fixture
def candidate_with_profile(db):
    user = User.objects.create_user(
        email='withprofile@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    profile = CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name='With Profile',
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        open_to_offers=True,
    )
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
    )
    return user, profile


@pytest.mark.django_db
def test_candidate_me_get_no_side_effect_on_missing_profile(candidate_without_profile):
    client = APIClient()
    client.force_authenticate(candidate_without_profile)

    # Calling GET should return 404 and NOT create a profile (B29)
    res = client.get('/api/candidates/me')
    assert res.status_code == 404
    assert not CandidateProfile.objects.filter(user=candidate_without_profile).exists()


@pytest.mark.django_db
def test_candidate_registration_creates_profile():
    client = APIClient()
    res = client.post('/api/auth/register', {
        'email': 'new_candidate_reg@example.com',
        'password': 'password123',
        'role': 'candidate',
    }, format='json')
    assert res.status_code == 201

    user = User.objects.get(email='new_candidate_reg@example.com')
    assert CandidateProfile.objects.filter(user=user).exists()

    client.force_authenticate(user)
    me_res = client.get('/api/candidates/me')
    assert me_res.status_code == 200
    assert me_res.data['public_id'] is not None


@pytest.mark.django_db
def test_profile_update_salary_validation(candidate_with_profile):
    user, _ = candidate_with_profile
    client = APIClient()
    client.force_authenticate(user)

    # salary_min > salary_max must fail with 422
    res = client.put('/api/candidates/me', {
        'salary_min': 200000,
        'salary_max': 100000,
    }, format='json')
    assert res.status_code == 422

    # Valid salary range must succeed
    res = client.put('/api/candidates/me', {
        'salary_min': 100000,
        'salary_max': 200000,
    }, format='json')
    assert res.status_code == 200
    assert res.data['salary_min'] == 100000
    assert res.data['salary_max'] == 200000


@pytest.mark.django_db
def test_profile_update_blocked_company_ids_validation(candidate_with_profile):
    user, _ = candidate_with_profile
    client = APIClient()
    client.force_authenticate(user)

    company = Company.objects.create(name='Real Company')
    random_uuid = str(uuid.uuid4())

    # Invalid company ID (not found in DB)
    res = client.put('/api/candidates/me', {
        'blocked_company_ids': [random_uuid],
    }, format='json')
    assert res.status_code == 422

    # Valid company ID
    res = client.put('/api/candidates/me', {
        'blocked_company_ids': [str(company.id)],
    }, format='json')
    assert res.status_code == 200
    assert str(company.id) in res.data['blocked_company_ids']


@pytest.mark.django_db
def test_verify_public_id(candidate_with_profile):
    user, profile = candidate_with_profile
    client = APIClient()

    # Short public_id must return 404
    assert client.get('/api/verify/C-123').status_code == 404

    # Confirmed league membership
    confirmed_date = timezone.now()
    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1250,
        confirmed_at=confirmed_date,
    )

    res = client.get(f'/api/verify/{profile.public_id}')
    assert res.status_code == 200
    assert res.data['valid'] is True
    assert res.data['specialization'] == Specialization.BACKEND
    assert res.data['grade'] == Grade.MIDDLE
    assert res.data['rating'] == 1250
    assert res.data['issued_at'] is not None

    # Filter with non-matching specialization
    res_other_spec = client.get(f'/api/verify/{profile.public_id}?specialization=frontend')
    assert res_other_spec.status_code == 200
    # Frontend league does not exist or unconfirmed
    assert res_other_spec.data['valid'] is False

    # Revoking publication consent causes valid=False
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=False,
    )
    res_revoked = client.get(f'/api/verify/{profile.public_id}')
    assert res_revoked.status_code == 200
    assert res_revoked.data['valid'] is False
