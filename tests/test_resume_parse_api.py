"""POST /api/candidates/me/resume: auth boundary, errors, rules fallback, no PII (AI-R7)."""
import logging
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
PROBLEM_JSON = "application/problem+json"


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
    assert response["Content-Type"].startswith(PROBLEM_JSON)


@pytest.mark.django_db
def test_missing_file_gets_422(client):
    response = client.post(URL, {}, format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.mark.django_db
def test_file_over_5_mb_gets_422(client):
    response = client.post(URL, _upload("cv.pdf", b"%PDF" + b"0" * (5 * 1024 * 1024)), format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.mark.django_db
def test_non_pdf_gets_422(client):
    response = client.post(URL, _upload("cv.txt", b"plain text"), format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "unreadable_pdf"


@pytest.mark.django_db
def test_corrupt_pdf_gets_422_without_exception_text(client):
    response = client.post(URL, _upload("cv.pdf", b"%PDF-1.4 garbage, no xref"), format="multipart")

    assert response.status_code == 422
    assert response["Content-Type"].startswith(PROBLEM_JSON)
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
    calls = []

    class BrokenGateway:
        name = "gigachat"

        def resume(self, redacted_text):
            calls.append(redacted_text)
            raise RuntimeError("adapter bug")

    monkeypatch.setattr(llm_gateway, "FakeLlm", BrokenGateway)
    response = client.post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")

    assert len(calls) == 1, "the view must go through the patched gateway"
    assert response.status_code == 200
    assert response.json()["source"] == "rules"
    assert response.json()["prefill"]["specialization"] == "backend"


@pytest.mark.django_db
def test_parser_bug_is_problem_json_500_without_the_message(client, monkeypatch, caplog):
    """A bug is not a bad PDF: problem+json 500, and the message (may quote the CV) is not logged."""

    def broken_parse(pdf_bytes, **kwargs):
        raise RuntimeError("could not parse 'ivan.ivanov@example.com'")

    monkeypatch.setattr(llm_gateway, "parse_resume", broken_parse)
    with caplog.at_level(logging.INFO):
        response = client.post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")

    assert response.status_code == 500
    assert response["Content-Type"].startswith(PROBLEM_JSON)
    assert response.json()["code"] == "resume_parse_failed"
    assert "ivan.ivanov" not in response.content.decode("utf-8")
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)
    for record in caplog.records:
        assert "ivan.ivanov" not in record.getMessage()
        assert record.exc_info is None or "ivan.ivanov" not in str(record.exc_info[1])


@pytest.mark.django_db
def test_invalid_pdf_magic_bytes_rejected(client):
    """File named .pdf with PDF mime but without %PDF magic bytes is rejected with 422 unreadable_pdf."""
    response = client.post(URL, _upload("cv.pdf", b"NOT-A-PDF-HEADER 12345678"), format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "unreadable_pdf"


@pytest.mark.django_db
def test_celery_task_timeout_falls_back_to_rules(client, monkeypatch):
    """When Celery task times out, view seamlessly falls back to inline rules."""
    from profiles import tasks

    class TimingOutTask:
        def apply_async(self, *args, **kwargs):
            class AsyncResult:
                def get(self, timeout=None):
                    raise TimeoutError("Celery task execution timed out")

            return AsyncResult()

    monkeypatch.setattr(tasks, "parse_resume_task", TimingOutTask())
    response = client.post(URL, _upload("cv.pdf", HERO_PDF.read_bytes()), format="multipart")
    assert response.status_code == 200
    assert response.json()["source"] == "rules"
    assert response.json()["prefill"]["specialization"] == "backend"

