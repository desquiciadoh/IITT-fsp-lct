"""Tests for Vacancies & Candidate Applications (Task BE-17).

Verifies:
1. Public vacancy listing & filtering.
2. Candidate direct application flow.
3. Automatic ContactGrant creation upon applying.
4. Contact access unmasked for employer after application.
5. 409 Conflict on duplicate application.
6. Employer application pipeline view and status updates.
7. Candidate application withdrawal.
"""

import pytest
from core.enums import ApplicationStatus, ContactGrantSource, PositionStatus, SalaryType, UserRole
from django.utils import timezone
from identity.models import User
from matching.models import Application, Company, CompanyMember, Position
from outreach.models import ContactGrant
from outreach.services import ContactAccessService
from profiles.models import CandidateContact, CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="applicant@example.com",
        password="TestPassword123!",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="Иван Заявитель",
        open_to_offers=True,
    )
    CandidateContact.objects.create(
        user=user,
        email="applicant@example.com",
        phone="+7 (999) 111-22-33",
        telegram="@ivan_applicant",
    )
    return user


@pytest.fixture
def employer_setup(db):
    company = Company.objects.create(
        name="Яндекс Вакансии",
        contact_email="hr@yandex-vacancies.ru",
    )
    employer_user = User.objects.create_user(
        email="recruiter@yandex-vacancies.ru",
        password="TestPassword123!",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    CompanyMember.objects.create(company=company, user=employer_user)
    return company, employer_user


@pytest.fixture
def public_position(db, employer_setup):
    company, _ = employer_setup
    return Position.objects.create(
        company=company,
        title="Senior Python Backend Developer",
        specialization="backend",
        grades=["senior"],
        must_skills=["Python", "Django", "PostgreSQL"],
        work_formats=["remote", "hybrid"],
        salary_min=300000,
        salary_max=450000,
        salary_type=SalaryType.GROSS,
        is_public=True,
        status=PositionStatus.OPEN,
        description="Разработка высоконагруженных микросервисов",
    )


@pytest.fixture
def private_position(db, employer_setup):
    company, _ = employer_setup
    return Position.objects.create(
        company=company,
        title="Private Need Developer",
        specialization="backend",
        grades=["middle"],
        must_skills=["Python"],
        work_formats=["remote"],
        salary_min=200000,
        salary_max=250000,
        salary_type=SalaryType.GROSS,
        is_public=False,
        status=PositionStatus.OPEN,
    )


@pytest.mark.django_db
class TestVacanciesAndApplications:
    def test_public_vacancies_list_and_filter(self, public_position, private_position):
        client = APIClient()

        # Listing vacancies only returns is_public=True
        resp = client.get("/api/vacancies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Senior Python Backend Developer"

        # Filter by specialization
        resp_filtered = client.get("/api/vacancies?specialization=frontend")
        assert resp_filtered.json()["total"] == 0

        # Filter by grades
        resp_grades = client.get("/api/vacancies?grades=senior")
        assert resp_grades.json()["total"] == 1

        # Vacancy detail
        resp_detail = client.get(f"/api/vacancies/{public_position.id}")
        assert resp_detail.status_code == 200
        assert resp_detail.json()["id"] == str(public_position.id)

        # Private position not available in public vacancies
        resp_private = client.get(f"/api/vacancies/{private_position.id}")
        assert resp_private.status_code == 404

    def test_candidate_apply_creates_grant_and_unmasks_contacts(
        self, candidate_user, employer_setup, public_position
    ):
        company, employer_user = employer_setup
        client = APIClient()
        client.force_authenticate(user=candidate_user)

        # Apply to public vacancy
        resp = client.post(
            f"/api/vacancies/{public_position.id}/apply",
            {"note": "Здравствуйте! Очень хочу у вас работать."},
            format="json",
        )
        assert resp.status_code == 201
        app_data = resp.json()
        assert app_data["status"] == ApplicationStatus.APPLIED
        assert app_data["note"] == "Здравствуйте! Очень хочу у вас работать."

        # Verify Application in DB
        app = Application.objects.get(position=public_position, candidate=candidate_user)
        assert app.status == ApplicationStatus.APPLIED

        # Verify ContactGrant created
        grant = ContactGrant.objects.get(
            candidate=candidate_user,
            company=company,
            source=ContactGrantSource.APPLICATION,
        )
        assert grant.is_active

        # Verify employer can now access contacts
        contacts = ContactAccessService.get_contacts(
            company_id=company.id,
            candidate_id=candidate_user.id,
            actor_id=employer_user.id,
        )
        assert contacts.email == "applicant@example.com"
        assert contacts.telegram == "@ivan_applicant"

        # Applying again returns 409 Conflict
        resp_dup = client.post(
            f"/api/vacancies/{public_position.id}/apply",
            {"note": "Повторная заявка"},
            format="json",
        )
        assert resp_dup.status_code == 409

    def test_candidate_applications_list_and_withdraw(
        self, candidate_user, public_position
    ):
        client = APIClient()
        client.force_authenticate(user=candidate_user)

        client.post(f"/api/vacancies/{public_position.id}/apply", {"note": "Test"})
        app = Application.objects.get(position=public_position, candidate=candidate_user)

        # List candidate applications
        resp = client.get("/api/candidates/me/applications")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Withdraw application
        resp_withdraw = client.post(f"/api/candidates/me/applications/{app.id}/withdraw")
        assert resp_withdraw.status_code == 200
        app.refresh_from_db()
        assert app.status == ApplicationStatus.WITHDRAWN

    def test_employer_application_pipeline_and_status_update(
        self, candidate_user, employer_setup, public_position
    ):
        company, employer_user = employer_setup

        # Candidate applies
        app = Application.objects.create(
            position=public_position,
            candidate=candidate_user,
            note="Резюме в профиле",
            status=ApplicationStatus.APPLIED,
        )

        client = APIClient()
        client.force_authenticate(user=employer_user)

        # Employer views applications for position
        resp = client.get(f"/api/positions/{public_position.id}/applications")
        assert resp.status_code == 200
        apps_data = resp.json()
        assert len(apps_data) == 1
        assert apps_data[0]["id"] == str(app.id)

        # Employer updates status to reviewing
        resp_review = client.patch(
            f"/api/positions/{public_position.id}/applications/{app.id}/status",
            {"status": ApplicationStatus.REVIEWING},
            format="json",
        )
        assert resp_review.status_code == 200
        app.refresh_from_db()
        assert app.status == ApplicationStatus.REVIEWING

        # Employer updates status to invited
        resp_invite = client.patch(
            f"/api/positions/{public_position.id}/applications/{app.id}/status",
            {"status": ApplicationStatus.INVITED},
            format="json",
        )
        assert resp_invite.status_code == 200
        app.refresh_from_db()
        assert app.status == ApplicationStatus.INVITED

        # Employer updates status to hired
        resp_hired = client.patch(
            f"/api/positions/{public_position.id}/applications/{app.id}/status",
            {"status": ApplicationStatus.HIRED},
            format="json",
        )
        assert resp_hired.status_code == 200
        app.refresh_from_db()
        assert app.status == ApplicationStatus.HIRED
