"""Tests for BE-21: Data protection extras (contacts encrypted at rest & per-employer PDF watermark)."""

from unittest.mock import MagicMock, patch

import pytest
from core.enums import (
    ConsentType,
    Grade,
    LeagueStatus,
    Specialization,
    UserRole,
)
from django.db import connection
from identity.models import AuditLog, Consent, User
from matching.models import Company, CompanyMember
from outreach.models import ContactGrant
from outreach.services import ContactAccessService
from profiles.models import (
    CandidateContact,
    CandidateProfile,
    generate_public_id,
)
from profiles.pdf_service import generate_player_card_pdf
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="encrypted_candidate@example.com",
        password="test-password-123",
        role=UserRole.CANDIDATE,
    )
    user.email_verified_at = "2025-01-01T00:00:00Z"
    user.save()
    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
        version="v1",
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="Ivan Crypto",
        specialization=Specialization.BACKEND,
        salary_floor=150000,
        salary_min=180000,
        salary_max=250000,
        open_to_offers=True,
    )
    from assessment.models import LeagueMembership

    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1350,
    )
    return user


@pytest.fixture
def employer_setup(db):
    user = User.objects.create_user(
        email="hr@corp-security.ru",
        password="test-password-123",
        role=UserRole.EMPLOYER,
    )
    user.email_verified_at = "2025-01-01T00:00:00Z"
    user.save()
    company = Company.objects.create(
        name="Security Corp",
        inn="7707083893",
        email_domain="corp-security.ru",
    )
    CompanyMember.objects.create(company=company, user=user)
    return {"user": user, "company": company}


@pytest.mark.django_db
class TestContactsEncryptedAtRest:
    def test_contacts_are_encrypted_in_database(self, candidate_user):
        """Contacts must be stored as Fernet ciphertext in SQL, and decrypted on read."""
        CandidateContact.objects.create(
            user=candidate_user,
            email="secret.personal@example.com",
            phone="+79998887766",
            telegram="@secret_dev",
        )

        # 1. Query raw database via SQL cursor to inspect raw column values
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT email, phone, telegram FROM candidate_contacts WHERE user_id = %s",
                [str(candidate_user.id)],
            )
            row = cursor.fetchone()
            raw_email, raw_phone, raw_telegram = row

        # Raw DB values must NOT contain plaintext sensitive data
        assert raw_email != "secret.personal@example.com"
        assert raw_phone != "+79998887766"
        assert raw_telegram != "@secret_dev"

        # Raw values must be Fernet tokens starting with gAAAAA
        assert raw_email.startswith("gAAAAA")
        assert raw_phone.startswith("gAAAAA")
        assert raw_telegram.startswith("gAAAAA")

        # 2. Query via Django ORM: transparently returns decrypted plaintext
        loaded = CandidateContact.objects.get(user=candidate_user)
        assert loaded.email == "secret.personal@example.com"
        assert loaded.phone == "+79998887766"
        assert loaded.telegram == "@secret_dev"

    def test_updating_contacts_maintains_encryption(self, candidate_user):
        """Updating contacts persists new ciphertexts and updates seamlessly."""
        contact = CandidateContact.objects.create(
            user=candidate_user,
            email="first@example.com",
            phone="+70000000000",
            telegram="@first",
        )

        contact.email = "updated@example.com"
        contact.phone = "+71112223344"
        contact.save()

        # Check raw database again
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT email, phone FROM candidate_contacts WHERE user_id = %s",
                [str(candidate_user.id)],
            )
            raw_email, raw_phone = cursor.fetchone()

        assert raw_email.startswith("gAAAAA")
        assert raw_phone.startswith("gAAAAA")
        assert "updated@example.com" not in raw_email

        # Fresh read
        refreshed = CandidateContact.objects.get(user=candidate_user)
        assert refreshed.email == "updated@example.com"
        assert refreshed.phone == "+71112223344"

    def test_legacy_plaintext_backward_compatibility(self, candidate_user):
        """If a raw plaintext string exists in the database, it is read safely without crashing."""
        # Insert raw plaintext directly bypassing get_prep_value
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO candidate_contacts (user_id, email, phone, telegram) "
                "VALUES (%s, %s, %s, %s)",
                [str(candidate_user.id), "raw_legacy@example.com", "+79990000000", "@legacy"],
            )

        loaded = CandidateContact.objects.get(user=candidate_user)
        assert loaded.email == "raw_legacy@example.com"
        assert loaded.phone == "+79990000000"
        assert loaded.telegram == "@legacy"

    def test_contact_access_service_returns_decrypted_contacts(self, candidate_user, employer_setup):
        """ContactAccessService retrieves decrypted contacts when grant is active."""
        CandidateContact.objects.create(
            user=candidate_user,
            email="confidential@example.com",
            phone="+79991234567",
            telegram="@confidential_coder",
        )
        company = employer_setup["company"]
        employer_user = employer_setup["user"]

        # Create active ContactGrant
        ContactGrant.objects.create(
            candidate=candidate_user,
            company=company,
            source="offer",
            source_id=candidate_user.id,
        )

        contacts = ContactAccessService.get_contacts(
            company_id=company.id,
            candidate_id=candidate_user.id,
            actor_id=employer_user.id,
        )
        assert contacts.email == "confidential@example.com"
        assert contacts.phone == "+79991234567"
        assert contacts.telegram == "@confidential_coder"
        assert contacts.full_name == "Ivan Crypto"


@pytest.mark.django_db
class TestEmployerPdfWatermark:
    def test_watermark_injected_in_pdf_html(self, candidate_user):
        """generate_player_card_pdf must inject company watermark into HTML template."""
        profile = candidate_user.candidate_profile
        watermark_text = "Security Corp · ИНН 7707083893"

        captured_html = {}
        mock_html_cls = MagicMock()

        def capture_html(string=None, url_fetcher=None):
            captured_html["string"] = string
            instance = MagicMock()
            instance.write_pdf.return_value = b"%PDF-1.4 watermarked"
            return instance

        mock_html_cls.side_effect = capture_html

        with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html_cls)}):
            pdf_bytes = generate_player_card_pdf(profile, watermark=watermark_text)
            assert pdf_bytes == b"%PDF-1.4 watermarked"

        html = captured_html["string"]
        assert "Security Corp · ИНН 7707083893" in html
        assert 'class="watermark"' in html
        assert 'class="watermark-notice"' in html

    def test_watermark_xss_escaping(self, candidate_user):
        """Watermark text must be properly HTML-escaped."""
        profile = candidate_user.candidate_profile
        malicious_watermark = 'Hacker Corp <script>alert("pwn")</script> & Co'

        captured_html = {}
        mock_html_cls = MagicMock()

        def capture_html(string=None, url_fetcher=None):
            captured_html["string"] = string
            instance = MagicMock()
            instance.write_pdf.return_value = b"%PDF-1.4 safe"
            return instance

        mock_html_cls.side_effect = capture_html

        with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html_cls)}):
            generate_player_card_pdf(profile, watermark=malicious_watermark)

        html = captured_html["string"]
        assert "<script>" not in html
        assert "&lt;script&gt;alert(&quot;pwn&quot;)&lt;/script&gt;" in html
        assert "Hacker Corp" in html

    def test_employer_card_pdf_export_endpoint(self, candidate_user, employer_setup):
        """Employer can export candidate card PDF with company watermark and audit trail."""
        profile = candidate_user.candidate_profile
        employer_user = employer_setup["user"]

        client = APIClient()
        client.force_authenticate(user=employer_user)

        with patch("matching.views.generate_player_card_pdf") as mock_gen:
            mock_gen.return_value = b"%PDF-1.4 watermarked-bytes"
            res = client.get(f"/api/talent/{profile.public_id}/card.pdf")

            assert res.status_code == 200
            assert res["Content-Type"] == "application/pdf"
            assert res.content == b"%PDF-1.4 watermarked-bytes"

            # Verify watermark was passed to generator
            mock_gen.assert_called_once()
            called_args, called_kwargs = mock_gen.call_args
            assert called_args[0] == profile
            assert "Security Corp" in called_kwargs["watermark"]
            assert "7707083893" in called_kwargs["watermark"]

        # Verify audit log was created
        audit_entry = AuditLog.objects.filter(
            actor_id=employer_user.id,
            action="talent_card_pdf_exported",
            target_id=str(profile.user_id),
        ).first()
        assert audit_entry is not None
        assert "Security Corp" in audit_entry.meta["watermark"]

    def test_employer_export_forbidden_for_invisible_candidate(self, candidate_user, employer_setup):
        """Exporting PDF for an invisible candidate returns 404 and writes audit log."""
        # Revoke publication consent to make candidate invisible
        Consent.objects.create(
            user=candidate_user,
            type=ConsentType.PUBLICATION,
            granted=False,
            version="v2",
        )
        profile = candidate_user.candidate_profile
        employer_user = employer_setup["user"]

        client = APIClient()
        client.force_authenticate(user=employer_user)

        res = client.get(f"/api/talent/{profile.public_id}/card.pdf")
        assert res.status_code == 404

        # Verify access denied audit log
        audit_entry = AuditLog.objects.filter(
            actor_id=employer_user.id,
            action="talent_card_access_denied",
        ).first()
        assert audit_entry is not None
        assert audit_entry.meta["reason"] == "candidate_not_visible"
