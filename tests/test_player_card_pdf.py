"""Tests for Player Card PDF generation and security (R7)."""

from unittest.mock import MagicMock, patch

import pytest
from core.enums import EvidenceSource, Grade, LeagueStatus, Specialization, UserRole
from core.errors import FSPAPIError
from identity.models import User
from profiles.models import CandidateProfile, CandidateSkill, Skill
from profiles.pdf_service import generate_player_card_pdf
from rest_framework.test import APIClient


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="candidate_pdf@example.com",
        password="secretpassword",
        role=UserRole.CANDIDATE,
    )
    user.email_verified_at = "2025-01-01T00:00:00Z"
    user.save()
    CandidateProfile.objects.create(
        user=user,
        public_id="C-PDF001",
        full_name="Alice Test",
    )
    from assessment.models import LeagueMembership

    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1200,
    )
    return user


@pytest.mark.django_db
class TestPlayerCardPdf:
    def test_pdf_import_error_raises_503(self, candidate):
        profile = candidate.candidate_profile
        with patch.dict("sys.modules", {"weasyprint": None}):
            with pytest.raises(FSPAPIError) as exc_info:
                generate_player_card_pdf(profile)
            assert exc_info.value.status_code == 503

    def test_pdf_endpoint_returns_503_on_import_error(self, candidate):
        client = APIClient()
        client.force_authenticate(user=candidate)
        with patch("profiles.views.generate_player_card_pdf") as mock_gen:
            mock_gen.side_effect = FSPAPIError(
                "pdf_service_unavailable",
                "PDF Service Unavailable",
                "PDF generation is currently unavailable",
                503,
            )
            res = client.get("/api/candidates/me/card.pdf")
            assert res.status_code == 503
            assert res.json()["code"] == "pdf_service_unavailable"

    def test_malicious_skill_escaping(self, candidate):
        profile = candidate.candidate_profile
        # Add malicious skills
        malicious_names = [
            '<img src="file:///etc/passwd">',
            "<script>alert(1)</script>",
            "http://169.254.169.254/",
        ]
        for idx, name in enumerate(malicious_names):
            skill = Skill.objects.create(id=f"skill-malicious-{idx}", name=name)
            CandidateSkill.objects.create(
                candidate=profile,
                skill=skill,
                source=EvidenceSource.DECLARED,
                level=0.8,
            )

        # Mock weasyprint HTML constructor to inspect the HTML content passed to it
        captured_html = {}
        mock_html_cls = MagicMock()

        def capture_html(string=None, url_fetcher=None):
            captured_html["string"] = string
            captured_html["fetcher"] = url_fetcher
            instance = MagicMock()
            instance.write_pdf.return_value = b"%PDF-1.4 test"
            return instance

        mock_html_cls.side_effect = capture_html

        with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html_cls)}):
            pdf_bytes = generate_player_card_pdf(profile)
            assert pdf_bytes == b"%PDF-1.4 test"

        html = captured_html["string"]
        assert '<img src="file:///etc/passwd">' not in html
        assert "<script>" not in html
        assert "&lt;img src=&quot;file:///etc/passwd&quot;&gt;" in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

        # Test the url_fetcher security: must reject SSRF
        fetcher = captured_html["fetcher"]
        assert fetcher is not None

        # Disallow file:// and http:// SSRF
        with pytest.raises(ValueError, match="External URL fetching is disabled"):
            fetcher("file:///etc/passwd")

        with pytest.raises(ValueError, match="External URL fetching is disabled"):
            fetcher("http://169.254.169.254/latest/meta-data")
