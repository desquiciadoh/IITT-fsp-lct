"""POST /api/candidates/me/resume: auth boundary, errors, rules fallback, no PII (AI-R7)."""
from pathlib import Path

import llm_gateway
import pytest
from core.enums import UserRole
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient

URL = "/api/candidates/me/resume"
HERO_PDF = Path(__file__).resolve().parent / "ai" / "fixtures" / "cv" / "cv_backend_middle.pdf"


@pytest.fixture
def client(db):
    user = User.objects.create_user(
        email="resume@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    api = APIClient()
    api.force_authenticate(user)
    return api


def _upload(name: str, content: bytes) -> dict:
    return {"file": SimpleUploadedFile(name, content, content_type="application/pdf")}


@pytest.mark.django_db
def test_anonymous_is_rejected():
    # SessionAuthentication sends no WWW-Authenticate header, so DRF answers 403, not 401
    response = APIClient().post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_non_pdf_gets_422(client):
    response = client.post(URL, _upload("cv.txt", b"plain text"), format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "unreadable_pdf"


@pytest.mark.django_db
def test_corrupt_pdf_gets_422_without_exception_text(client):
    response = client.post(URL, _upload("cv.pdf", b"%PDF-1.4 garbage, no xref"), format="multipart")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unreadable_pdf"
    for leak in ("Error", "Traceback", "pypdf", "pdfplumber", "xref", "EOF"):
        assert leak not in body["detail"]


@pytest.mark.django_db
def test_hero_cv_prefill_without_contacts(client):
    response = client.post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rules"
    assert body["prefill"]["specialization"] == "backend"
    assert "python" in body["prefill"]["skills"]
    # contacts stay local until the candidate confirms the form: none in the response
    raw = response.content.decode("utf-8")
    for pii in ("Иванов", "ivan.ivanov@example.com", "111-22-33", "ivan_backend", "ivan-dev"):
        assert pii not in raw


@pytest.mark.django_db
def test_failing_gateway_still_answers_with_rules(client, monkeypatch):
    """A gateway that raises does not break the upload: 200 with source="rules"."""

    class BrokenGateway:
        name = "gigachat"

        def resume(self, redacted_text):
            raise RuntimeError("adapter bug")

    monkeypatch.setattr(llm_gateway, "FakeLlm", BrokenGateway)
    response = client.post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")

    assert response.status_code == 200
    assert response.json()["source"] == "rules"
    assert response.json()["prefill"]["specialization"] == "backend"
