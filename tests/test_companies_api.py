import pytest
from core.enums import UserRole
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember
from rest_framework.test import APIClient


@pytest.fixture
def candidate_client(db):
    user = User.objects.create_user(
        email="cand.search@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def employer_without_company(db):
    user = User.objects.create_user(
        email="emp.new@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.fixture
def employer_with_company(db):
    user = User.objects.create_user(
        email="emp.exists@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="Existing Tech LLC")
    CompanyMember.objects.create(company=company, user=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client, company


@pytest.mark.django_db
def test_companies_search_for_candidates(candidate_client):
    Company.objects.create(name="Alpha Corp")
    Company.objects.create(name="Beta Tech")
    Company.objects.create(name="Gamma Corp")

    # Without search param -> 422
    res_no_search = candidate_client.get("/api/companies")
    assert res_no_search.status_code == 422
    assert res_no_search.json().get("code") == "validation_failed"

    # Search with 1 character (< 2 chars) -> 422
    res_short = candidate_client.get("/api/companies?search=A")
    assert res_short.status_code == 422
    assert res_short.json().get("code") == "validation_failed"

    # Search with 2+ characters -> 200 paginated
    res_search = candidate_client.get("/api/companies?search=Alpha")
    assert res_search.status_code == 200
    data = res_search.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["pages"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Alpha Corp"
    assert set(data["items"][0].keys()) == {"id", "name"}


@pytest.mark.django_db
def test_companies_search_pagination(candidate_client):
    Company.objects.create(name="Tech Alpha")
    Company.objects.create(name="Tech Beta")
    Company.objects.create(name="Tech Gamma")

    res_page1 = candidate_client.get("/api/companies?search=Tech&page=1&size=2")
    assert res_page1.status_code == 200
    data1 = res_page1.json()
    assert data1["total"] == 3
    assert data1["page"] == 1
    assert data1["pages"] == 2
    assert len(data1["items"]) == 2

    res_page2 = candidate_client.get("/api/companies?search=Tech&page=2&size=2")
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert data2["total"] == 3
    assert data2["page"] == 2
    assert len(data2["items"]) == 1


@pytest.mark.django_db
def test_company_creation_race_integrity_error(employer_without_company, monkeypatch):
    user, client = employer_without_company
    from django.db import IntegrityError

    # Simulate race where exists() check returned False, but DB insert raises IntegrityError
    def mock_create(*args, **kwargs):
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(CompanyMember.objects, "create", mock_create)

    payload = {"name": "Race Condition LLC"}
    res = client.post("/api/companies", payload, format="json")
    assert res.status_code == 400
    assert res.json().get("code") == "company_already_exists"


@pytest.mark.django_db
def test_admin_can_view_all_offers_without_company(db):
    from core.enums import OfferStatus, SalaryType
    from outreach.models import Offer

    admin_user = User.objects.create_user(
        email="admin@example.com",
        password="password123",
        role=UserRole.ADMIN,
        is_staff=True,
        email_verified_at=timezone.now(),
    )
    candidate = User.objects.create_user(
        email="candidate@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="Acme Corp")
    offer = Offer.objects.create(
        company=company,
        candidate=candidate,
        title="Senior Developer",
        description="Exciting role",
        salary_min=200000,
        salary_max=300000,
        salary_type=SalaryType.GROSS,
        contact_channel="email",
        contact_value="hr@acme.com",
        status=OfferStatus.SENT,
    )

    admin_client = APIClient()
    admin_client.force_authenticate(user=admin_user)

    # Admin should NOT get 403 company_required
    res = admin_client.get("/api/offers")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1
    assert any(item["id"] == str(offer.id) for item in data["items"])

    # Filter by company_id
    res_company = admin_client.get(f"/api/offers?company_id={company.id}")
    assert res_company.status_code == 200
    assert len(res_company.json()["items"]) >= 1

    # Filter by candidate_id
    res_candidate = admin_client.get(f"/api/offers?candidate_id={candidate.id}")
    assert res_candidate.status_code == 200
    assert len(res_candidate.json()["items"]) >= 1


@pytest.mark.django_db
def test_companies_anonymous_unauthorized():
    client = APIClient()
    res = client.get("/api/companies")
    assert res.status_code in (401, 403)


@pytest.mark.django_db
def test_candidate_cannot_create_company(candidate_client):
    res = candidate_client.post("/api/companies", {"name": "Candidate Rogue Corp"}, format="json")
    assert res.status_code == 403


@pytest.mark.django_db
def test_employer_creates_company(employer_without_company):
    user, client = employer_without_company
    assert not user.company_memberships.exists()

    payload = {
        "name": "New Venture LLC",
        "inn": "7707083893",
        "website": "https://venture.example.com",
    }
    res = client.post("/api/companies", payload, format="json")
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "New Venture LLC"
    assert data["inn"] == "7707083893"

    # Verify user is now a member of this company
    membership = CompanyMember.objects.filter(user=user).first()
    assert membership is not None
    assert membership.company.id == Company.objects.get(name="New Venture LLC").id


@pytest.mark.django_db
def test_employer_cannot_create_second_company(employer_with_company):
    user, client, company = employer_with_company
    payload = {"name": "Second Corp LLC"}
    res = client.post("/api/companies", payload, format="json")
    assert res.status_code == 400
    data = res.json()
    assert data.get("code") == "company_already_exists"


@pytest.mark.django_db
def test_company_creation_validation_failed(employer_without_company):
    user, client = employer_without_company
    # Missing required 'name'
    res = client.post("/api/companies", {}, format="json")
    assert res.status_code == 422
    data = res.json()
    assert data.get("code") == "validation_failed"
