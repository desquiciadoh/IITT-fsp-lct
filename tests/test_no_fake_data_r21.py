import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from core.enums import UserRole
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from identity.models import User
from pypdf import PdfWriter
from rest_framework.test import APIClient


@pytest.fixture
def candidate_client(db):
    user = User.objects.create_user(
        email="cand.resume@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_dummy_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.getvalue()


@pytest.mark.django_db
def test_lab_report_serves_fixture_when_no_report():
    client = APIClient()
    report_file = Path(settings.BASE_DIR) / "validation" / "out" / "report.json"
    if report_file.exists():
        report_file.unlink()

    res = client.get("/api/lab/report")
    assert res.status_code == 200
    data = res.json()
    assert data.get("synthetic_fixture") is True
    assert "assessment" in data
    assert "matching" in data


@pytest.mark.django_db
def test_lab_report_serves_report_when_present(tmp_path, monkeypatch):
    client = APIClient()
    report_dir = tmp_path / "validation" / "out"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "report.json"

    real_data = {
        "generated_at": "2026-10-10T12:00:00Z",
        "git_sha": "production-sha",
        "synthetic_fixture": False,
        "assessment": {
            "simulees": 2000,
            "exact_acc": 0.89,
            "adjacent_acc": 0.99,
            "qwk": 0.92,
            "retest_same_grade": 0.91,
            "retest_r": 0.95,
            "median_len": 11.5,
            "max_family_exposure": 0.12,
            "collision_rate": 0.001,
            "generator_errors": 0,
            "confusion": [[250, 0, 0, 0], [0, 250, 0, 0], [0, 0, 250, 0], [0, 0, 0, 250]],
            "tif": {"theta": [-2.0, 0.0, 2.0], "info": [1.5, 4.8, 1.8]},
            "leak_attack": [{"leak_share": 0.0, "static_dtheta": 0.0, "parametric_dtheta": 0.0}],
        },
        "matching": {
            "candidates": 600,
            "needs": 60,
            "non_fsp_parity": 0.98,
            "pool_p95_ms": 28.0,
            "systems": [
                {"name": "production", "ndcg10": 0.91, "p10": 0.85, "r50": 0.93, "mrr": 0.88}
            ],
        },
    }
    report_file.write_text(json.dumps(real_data), encoding="utf-8")

    monkeypatch.setattr(settings, "BASE_DIR", str(tmp_path))

    res = client.get("/api/lab/report")
    assert res.status_code == 200
    data = res.json()
    assert data.get("synthetic_fixture") is False
    assert data.get("git_sha") == "production-sha"


@pytest.mark.django_db
def test_lab_report_corrupt_report_returns_500_logged(tmp_path, monkeypatch):
    client = APIClient()
    report_dir = tmp_path / "validation" / "out"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "report.json"
    # Also add a valid fixture so we verify corrupt report does NOT fall back to fixture
    fixture_file = report_dir / "report.fixture.json"
    fixture_file.write_text(json.dumps({"synthetic_fixture": True}), encoding="utf-8")

    # Corrupt report.json content
    report_file.write_text("{invalid_json: true, corrupt...", encoding="utf-8")

    monkeypatch.setattr(settings, "BASE_DIR", str(tmp_path))

    with patch("assessment.views.logger.exception") as mock_log:
        res = client.get("/api/lab/report")
        assert res.status_code == 500
        assert res.json().get("code") == "report_unreadable"
        assert mock_log.called


@pytest.mark.django_db
def test_lab_report_corrupt_fixture_returns_500(tmp_path, monkeypatch):
    client = APIClient()
    report_dir = tmp_path / "validation" / "out"
    report_dir.mkdir(parents=True)
    fixture_file = report_dir / "report.fixture.json"
    fixture_file.write_text("{invalid_fixture...", encoding="utf-8")

    monkeypatch.setattr(settings, "BASE_DIR", str(tmp_path))

    with patch("assessment.views.logger.exception") as mock_log:
        res = client.get("/api/lab/report")
        assert res.status_code == 500
        assert res.json().get("code") == "report_unreadable"
        assert mock_log.called


@pytest.mark.django_db
def test_lab_report_missing_both_returns_500(tmp_path, monkeypatch):
    client = APIClient()
    report_dir = tmp_path / "validation" / "out"
    report_dir.mkdir(parents=True)
    # Neither report.json nor report.fixture.json exists

    monkeypatch.setattr(settings, "BASE_DIR", str(tmp_path))

    res = client.get("/api/lab/report")
    assert res.status_code == 500
    assert res.json().get("code") == "report_unreadable"


@pytest.mark.django_db
def test_resume_stub_returns_source_stub_and_empty_skills(candidate_client):
    pdf_bytes = make_dummy_pdf()
    pdf_file = SimpleUploadedFile("resume.pdf", pdf_bytes, content_type="application/pdf")

    res = candidate_client.post("/api/candidates/me/resume", {"file": pdf_file}, format="multipart")
    assert res.status_code == 200
    data = res.json()
    assert data.get("source") == "stub"
    prefill = data.get("prefill", {})
    assert prefill.get("skills") == []
