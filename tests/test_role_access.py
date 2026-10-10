import pytest
from core.enums import OfferStatus, SalaryType, UserRole
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember
from outreach.models import Offer
from rest_framework.test import APIClient


@pytest.fixture
def users_and_company(db):
    candidate = User.objects.create_user(
        email="candidate.access@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    employer = User.objects.create_user(
        email="employer.access@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(
        name="Access Test Company",
        contact_email="hr@access.test",
    )
    CompanyMember.objects.create(company=company, user=employer)
    offer = Offer.objects.create(
        company=company,
        candidate=candidate,
        created_by=employer,
        title="Backend Engineer",
        description="Role details",
        salary_min=100000,
        salary_max=150000,
        salary_type=SalaryType.GROSS,
        contact_channel="email",
        contact_value="hr@access.test",
        status=OfferStatus.SENT,
    )
    return candidate, employer, offer


@pytest.mark.django_db
def test_candidate_cannot_access_employer_endpoints(users_and_company):
    candidate, _, _ = users_and_company
    client = APIClient()
    client.force_authenticate(candidate)

    assert client.get("/api/companies/me").status_code == 403
    assert client.get("/api/positions").status_code == 403
    assert client.get("/api/talent/search").status_code == 403


@pytest.mark.django_db
def test_employer_cannot_access_candidate_only_endpoints(users_and_company):
    _, employer, _ = users_and_company
    client = APIClient()
    client.force_authenticate(employer)

    assert client.post("/api/assessments").status_code == 403
    assert client.post("/api/fsp/link", {"participant_id": "FSP-000123"}).status_code == 403


@pytest.mark.django_db
def test_time_travel_requires_an_authenticated_user():
    client = APIClient()

    assert client.post("/api/demo/time-travel", {"days": 30}).status_code == 403


@pytest.mark.django_db
def test_offer_detail_is_scoped_to_participant(users_and_company):
    candidate, _, offer = users_and_company
    unrelated = User.objects.create_user(
        email="unrelated.access@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(unrelated)

    response = client.get(f"/api/offers/{offer.id}")

    assert response.status_code == 404

    client.force_authenticate(candidate)
    assert client.get(f"/api/offers/{offer.id}").status_code == 200
