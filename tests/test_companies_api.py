import pytest
from core.enums import UserRole
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember
from rest_framework.test import APIClient


@pytest.fixture
def candidate_client(db):
    user = User.objects.create_user(
        email='cand.search@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def employer_without_company(db):
    user = User.objects.create_user(
        email='emp.new@example.com',
        password='password123',
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.fixture
def employer_with_company(db):
    user = User.objects.create_user(
        email='emp.exists@example.com',
        password='password123',
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name='Existing Tech LLC')
    CompanyMember.objects.create(company=company, user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client, company


@pytest.mark.django_db
def test_companies_search_for_candidates(candidate_client):
    Company.objects.create(name='Alpha Corp')
    Company.objects.create(name='Beta Tech')
    Company.objects.create(name='Gamma Corp')

    # All companies (minimal id and name)
    res = candidate_client.get('/api/companies')
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 3
    for item in data:
        assert set(item.keys()) == {'id', 'name'}

    # Search with filter
    res_search = candidate_client.get('/api/companies?search=Alpha')
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert len(search_data) == 1
    assert search_data[0]['name'] == 'Alpha Corp'


@pytest.mark.django_db
def test_companies_anonymous_unauthorized():
    client = APIClient()
    res = client.get('/api/companies')
    assert res.status_code in (401, 403)


@pytest.mark.django_db
def test_candidate_cannot_create_company(candidate_client):
    res = candidate_client.post('/api/companies', {'name': 'Candidate Rogue Corp'}, format='json')
    assert res.status_code == 403


@pytest.mark.django_db
def test_employer_creates_company(employer_without_company):
    user, client = employer_without_company
    assert not user.company_memberships.exists()

    payload = {
        'name': 'New Venture LLC',
        'inn': '7701234567',
        'website': 'https://venture.example.com',
    }
    res = client.post('/api/companies', payload, format='json')
    assert res.status_code == 201
    data = res.json()
    assert data['name'] == 'New Venture LLC'
    assert data['inn'] == '7701234567'

    # Verify user is now a member of this company
    membership = CompanyMember.objects.filter(user=user).first()
    assert membership is not None
    assert membership.company.id == Company.objects.get(name='New Venture LLC').id


@pytest.mark.django_db
def test_employer_cannot_create_second_company(employer_with_company):
    user, client, company = employer_with_company
    payload = {'name': 'Second Corp LLC'}
    res = client.post('/api/companies', payload, format='json')
    assert res.status_code == 400
    data = res.json()
    assert data.get('code') == 'company_already_exists'


@pytest.mark.django_db
def test_company_creation_validation_failed(employer_without_company):
    user, client = employer_without_company
    # Missing required 'name'
    res = client.post('/api/companies', {}, format='json')
    assert res.status_code == 422
    data = res.json()
    assert data.get('code') == 'validation_failed'
