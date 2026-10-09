"""Unit tests for LLM Gateway orchestration (AI-R2, AI-R10, AI-R11, AI-R12, AI-R13)."""
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from llm_gateway import (
    FakeLlm,
    GatewayConfig,
    UnreadablePdf,
    get_gateway,
    parse_jd,
    parse_resume,
)
from llm_gateway.base import LlmUnavailable
from llm_gateway.types import ResumeDraft

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class InMemoryCache:
    """Simple dict-backed cache for unit testing."""
    def __init__(self):
        self.store = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ttl: int):
        self.store[key] = value


def test_parse_resume_empty_pdf_raises_unreadable():
    with pytest.raises(UnreadablePdf):
        parse_resume(b"")

    with pytest.raises(UnreadablePdf):
        parse_resume(b"corrupted invalid not-a-pdf bytes")


def test_parse_resume_scanned_pdf_raises_unreadable():
    scanned_path = FIXTURES_DIR / "cv" / "cv_scanned_image_only.pdf"
    assert scanned_path.exists()
    with pytest.raises(UnreadablePdf):
        parse_resume(scanned_path.read_bytes())


def test_parse_resume_caching_and_fallback():
    """Verify AI-R2: truthful source, cache only validated LLM calls, transparent fallback."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cache = InMemoryCache()

    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.config = GatewayConfig(provider="gigachat", auth_key="dummy-key", model="GigaChat-2")

    # 1. Provider fails -> source='rules', correct fallback_reason, cache empty
    mock_gw.resume.side_effect = LlmUnavailable("Auth failure 401", reason="http_error")
    res_fail = parse_resume(pdf_bytes, gateway=mock_gw, cache=cache)

    assert res_fail.source == "rules"
    assert res_fail.fallback_reason == "http_error"
    assert len(cache.store) == 0, "Cache must remain empty on fallback to rules"

    # 2. Provider succeeds -> source='llm', 1 cache entry
    mock_gw.resume.side_effect = None
    mock_gw.resume.return_value = ResumeDraft(
        specialization="backend",
        claimed_grade="middle",
        years_experience=3.5,
        roles=["Backend Developer"],
        skills_raw=["Python", "FastAPI"],
        work_formats=["remote"],
        salary_min=220000,
        salary_max=280000,
        salary_type="net",
        city="Москва",
        about="Middle backend developer",
        experience_text="3.5 years of experience",
    )

    res_ok = parse_resume(pdf_bytes, gateway=mock_gw, cache=cache)
    assert res_ok.source == "llm"
    assert res_ok.fallback_reason is None
    assert len(cache.store) == 1
    assert mock_gw.resume.call_count == 2  # 1 from fail attempt, 1 from success

    # 3. Second call with same text -> cache hit, gateway is NOT called again
    res_cached = parse_resume(pdf_bytes, gateway=mock_gw, cache=cache)
    assert res_cached.source == "llm"
    assert res_cached.prefill["specialization"] == "backend"
    assert mock_gw.resume.call_count == 2, "Gateway must not be called on cache hit"

    # 4. Corrupted cache entry -> ignored and recomputed
    for k in list(cache.store.keys()):
        cache.store[k] = json.dumps({"source": "llm", "draft": "corrupted non-dict"})
    _ = parse_resume(pdf_bytes, gateway=mock_gw, cache=cache)
    assert mock_gw.resume.call_count == 3


def test_serializer_fit_prefill_shape():
    """Verify AI-R11: unknown strings are '', lists are [], numbers are None."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_frontend_junior.pdf").read_bytes()

    res = parse_resume(pdf_bytes, gateway=FakeLlm())
    prefill = res.prefill

    # Strings must not be None
    assert isinstance(prefill["city"], str)
    assert isinstance(prefill["about"], str)
    assert isinstance(prefill["experience_text"], str)

    # Lists must be lists
    assert isinstance(prefill["roles"], list)
    assert isinstance(prefill["work_formats"], list)
    assert isinstance(prefill["skills"], list)

    # Numbers can be int/float or None
    assert prefill["years_experience"] is None or isinstance(prefill["years_experience"], (int, float))
    assert prefill["salary_min"] is None or isinstance(prefill["salary_min"], int)
    assert prefill["salary_max"] is None or isinstance(prefill["salary_max"], int)


def test_parse_jd_orchestration_and_blueprint():
    """Verify parse_jd, ML blueprint_for conversion (AI-R13), and serializer shape."""
    jd_text = (FIXTURES_DIR / "jd" / "jd_backend_must_nice.txt").read_text(encoding="utf-8")
    cache = InMemoryCache()

    res = parse_jd(jd_text, gateway=FakeLlm(), cache=cache)

    assert res.source == "rules"
    assert res.draft["specialization"] == "backend"
    assert "python" in res.draft["must_skills"]
    assert "django" in res.draft["must_skills"]
    assert "postgresql" in res.draft["must_skills"]
    assert "remote" in res.draft["work_formats"]
    assert res.draft["salary_min"] == 320000
    assert res.draft["salary_max"] == 420000
    assert res.draft["salary_type"] == "net"

    # Unknown strings should be empty strings, not None
    assert isinstance(res.draft["team_context"], str)
    assert isinstance(res.draft["location"], str)

    # Test monkeypatched blueprint_for conversions
    import sys
    import types

    fake_mod = types.ModuleType("assessment.engine.blueprint")

    # Case A: returns list of tuples -> converted to list of dicts
    fake_mod.blueprint_for = lambda spec, skills: [("backend.python", 0.6), ("backend.databases", 0.4)]
    sys.modules["assessment.engine.blueprint"] = fake_mod
    try:
        res_bp = parse_jd(jd_text, gateway=FakeLlm())
        assert res_bp.blueprint == [
            {"topic": "backend.python", "weight": 0.6},
            {"topic": "backend.databases", "weight": 0.4},
        ]

        # Case B: raises ValueError -> returns [] and doesn't crash
        fake_mod.blueprint_for = MagicMock(side_effect=ValueError("Invalid spec"))
        res_bp_err = parse_jd(jd_text, gateway=FakeLlm())
        assert res_bp_err.blueprint == []
    finally:
        sys.modules.pop("assessment.engine.blueprint", None)


def test_observability_logging_privacy(caplog):
    """Verify AI-R12: structured log_llm_call with no CV text and no PII."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()

    with caplog.at_level(logging.INFO):
        res = parse_resume(pdf_bytes, gateway=FakeLlm())

    llm_logs = [r for r in caplog.records if r.getMessage().startswith("llm_call")]
    assert len(llm_logs) >= 1, "Expected at least one structured llm_call log record"

    rec = llm_logs[0]
    # Verify presence of all required fields in the log record
    assert "kind" in rec.__dict__ or "kind" in rec.message
    assert "source" in rec.__dict__ or "source" in rec.message

    # Crucial 152-FZ verification:
    # No candidate personal names or phone numbers appear in any captured log message
    for contact_val in res.contacts.values():
        if contact_val and len(contact_val) > 4:
            for log_rec in caplog.records:
                assert contact_val.lower() not in log_rec.getMessage().lower()


def test_get_gateway_factory():
    gw_fake = get_gateway(GatewayConfig(provider="fake"))
    assert gw_fake.name == "fake"

    # GigaChat with dummy key
    gw_giga = get_gateway(GatewayConfig(provider="gigachat", auth_key="dummy-key"))
    assert gw_giga.name == "gigachat"
