import pytest
from core.enums import ConsentType, Specialization, UserRole
from django.conf import settings
from django.core.cache import cache
from identity.models import AuditLog, Consent, User
from matching.models import Company, CompanyMember
from profiles.models import CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestR26MissingTests:
    def test_wsgi_and_asgi_import_smoke(self):
        """Smoke test verifying WSGI and ASGI applications can be imported and initialized."""
        import config.asgi
        import config.wsgi

        assert config.wsgi.application is not None
        assert callable(config.wsgi.application)

        assert config.asgi.application is not None
        assert callable(config.asgi.application)

    def test_role_admin_register_gives_400(self):
        """Registering with role=admin must be rejected with 400 Bad Request."""
        client = APIClient()
        payload = {
            "email": "hacker_admin@example.com",
            "password": "secret_password_123",
            "role": "admin",
        }
        res = client.post("/api/auth/register", payload, format="json")
        assert res.status_code == 400
        data = res.json()
        assert data.get("code") == "invalid_role"
        assert User.objects.filter(email="hacker_admin@example.com").exists() is False

    def test_persona_off_outside_demo_mode(self, monkeypatch):
        """Persona endpoint is disabled (403) when DEMO_MODE is False."""
        monkeypatch.setattr(settings, "DEMO_MODE", False)
        client = APIClient()
        res = client.post("/api/demo/persona", {"persona": "candidate_fsp"}, format="json")
        assert res.status_code == 403
        data = res.json()
        assert data.get("code") == "forbidden"

    def test_unknown_persona_gives_422(self, monkeypatch):
        """Supplying an unknown persona gives 422 Unprocessable Entity."""
        monkeypatch.setattr(settings, "DEMO_MODE", True)
        client = APIClient()
        res = client.post("/api/demo/persona", {"persona": "nonexistent_persona"}, format="json")
        assert res.status_code == 422
        data = res.json()
        assert data.get("code") == "validation_failed"

    def test_non_demo_user_rejected_from_persona_switch(self, monkeypatch):
        """An authenticated real non-demo user cannot switch personas (403)."""
        monkeypatch.setattr(settings, "DEMO_MODE", True)
        real_user = User.objects.create_user(
            email="real_user@production.com",
            password="real_password_123",
            role=UserRole.CANDIDATE,
            is_demo=False,
        )
        client = APIClient()
        client.force_authenticate(user=real_user)
        res = client.post("/api/demo/persona", {"persona": "candidate_fsp"}, format="json")
        assert res.status_code == 403
        data = res.json()
        assert data.get("code") == "forbidden"

    def test_two_employers_with_same_email_local_part(self):
        """Two employers with the same email local part (hr@alpha.com and hr@beta.com) register and operate independently."""
        cache.clear()
        client = APIClient()

        # Register employer A
        res_a = client.post(
            "/api/auth/register",
            {"email": "hr@alpha-corp.com", "password": "password123", "role": "employer"},
            format="json",
        )
        assert res_a.status_code == 201

        # Register employer B with same local part 'hr'
        res_b = client.post(
            "/api/auth/register",
            {"email": "hr@beta-corp.com", "password": "password123", "role": "employer"},
            format="json",
        )
        assert res_b.status_code == 201

        user_a = User.objects.get(email="hr@alpha-corp.com")
        user_b = User.objects.get(email="hr@beta-corp.com")
        assert user_a.id != user_b.id

        company_a = Company.objects.create(name="Alpha Corp")
        company_b = Company.objects.create(name="Beta Corp")

        CompanyMember.objects.create(company=company_a, user=user_a)
        CompanyMember.objects.create(company=company_b, user=user_b)

        assert user_a.company_memberships.first().company == company_a
        assert user_b.company_memberships.first().company == company_b

    def test_company_required_gives_403(self):
        """Employer without an associated company gets 403 company_required."""
        employer = User.objects.create_user(
            email="lonely_recruiter@example.com",
            password="password123",
            role=UserRole.EMPLOYER,
        )
        client = APIClient()
        client.force_authenticate(user=employer)

        # Attempt to create a position without a company
        payload = {
            "title": "Backend Lead",
            "specialization": Specialization.BACKEND,
            "salary_min": 200000,
            "salary_max": 300000,
            "salary_type": "gross",
        }
        res = client.post("/api/positions", payload, format="json")
        assert res.status_code == 403
        data = res.json()
        assert data.get("code") == "company_required"

    def test_invisible_talent_card_gives_404_and_creates_audit_log(self):
        """Requesting an invisible candidate's talent card returns 404 and writes an AuditLog entry."""
        candidate = User.objects.create_user(
            email="private_candidate@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        profile = CandidateProfile.objects.create(
            user=candidate,
            public_id=generate_public_id(),
            specialization=Specialization.BACKEND,
        )
        # Publication consent revoked (not granted)
        Consent.objects.create(
            user=candidate,
            type=ConsentType.PUBLICATION,
            granted=False,
        )

        employer = User.objects.create_user(
            email="recruiter@acme.com",
            password="password123",
            role=UserRole.EMPLOYER,
        )
        company = Company.objects.create(name="Acme Corp")
        CompanyMember.objects.create(company=company, user=employer)

        client = APIClient()
        client.force_authenticate(user=employer)

        assert not AuditLog.objects.filter(
            action="talent_card_access_denied",
            target_id=str(candidate.id),
        ).exists()

        res = client.get(f"/api/talent/{profile.public_id}")
        assert res.status_code == 404
        data = res.json()
        assert data.get("code") == "not_found"

        new_audit = AuditLog.objects.filter(
            action="talent_card_access_denied",
            target_id=str(candidate.id),
        ).first()
        assert new_audit is not None
        assert new_audit.actor_id == employer.id
        assert new_audit.meta.get("company_id") == str(company.id)
        assert new_audit.meta.get("reason") == "candidate_not_visible"
