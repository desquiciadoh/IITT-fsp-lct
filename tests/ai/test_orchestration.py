"""Unit tests for LLM Gateway orchestration (AI-R2, AI-R10, AI-R11, AI-R12, AI-R13)."""
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from llm_gateway import (
    FakeLlm,
    GatewayConfig,
    UnreadablePdf,
    extract_text,
    get_gateway,
    parse_jd,
    parse_resume,
    pipeline,
    redact,
)
from llm_gateway.base import RESUME_PROMPT, LlmSchemaError, LlmUnavailable, load_prompt
from llm_gateway.gigachat import GigaChatLlm
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
    mock_gw.resume.return_value = _llm_draft(
        skills_raw=["Python", "FastAPI"],
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


def _llm_draft(**overrides) -> ResumeDraft:
    fields = {
        "specialization": "backend", "claimed_grade": "middle", "years_experience": 3.5,
        "roles": ["Backend Developer"], "skills_raw": ["Python"], "work_formats": ["remote"],
        "salary_min": 220000, "salary_max": 280000, "salary_type": "net", "city": "Москва",
        "about": "", "experience_text": "",
    }
    fields.update(overrides)
    return ResumeDraft(**fields)


def _gigachat_mock() -> MagicMock:
    gw = MagicMock()
    gw.name = "gigachat"
    gw.config = GatewayConfig(provider="gigachat", auth_key="dummy-key", model="GigaChat-2")
    return gw


@pytest.mark.parametrize(
    ("side_effect", "reason"),
    [
        (LlmUnavailable("down", reason="timeout"), "timeout"),
        (LlmUnavailable("503", reason="http_error"), "http_error"),
        (LlmSchemaError("bad json twice", reason="schema"), "schema"),
        (TimeoutError("timed out"), "timeout"),
        (RuntimeError("bug in an adapter"), "error"),
    ],
)
def test_gateway_failure_falls_back_with_reason(side_effect, reason):
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cache = InMemoryCache()
    gw = _gigachat_mock()
    gw.resume.side_effect = side_effect

    res = parse_resume(pdf_bytes, gateway=gw, cache=cache)

    assert res.source == "rules"
    assert res.fallback_reason == reason
    assert res.prefill["specialization"] == "backend"  # the rules answer, not an empty form
    assert cache.store == {}


def test_llm_answer_without_usable_fields_is_a_schema_fallback():
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    gw = _gigachat_mock()
    gw.resume.return_value = ResumeDraft()

    res = parse_resume(pdf_bytes, gateway=gw)

    assert (res.source, res.fallback_reason) == ("rules", "schema")


def test_rules_reasons_provider_fake_and_no_key():
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_frontend_junior.pdf").read_bytes()

    res_fake = parse_resume(pdf_bytes, gateway=FakeLlm())
    assert (res_fake.source, res_fake.fallback_reason) == ("rules", "provider_fake")

    no_key = get_gateway(GatewayConfig(provider="gigachat", auth_key=None))
    res_no_key = parse_resume(pdf_bytes, gateway=no_key)
    assert (res_no_key.source, res_no_key.fallback_reason) == ("rules", "no_key")


def test_cache_entry_with_invalid_enums_is_ignored():
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cache = InMemoryCache()
    gw = _gigachat_mock()
    gw.resume.return_value = _llm_draft()

    parse_resume(pdf_bytes, gateway=gw, cache=cache)
    (key, raw), = cache.store.items()
    entry = json.loads(raw)
    entry["draft"]["specialization"] = "fullstack"  # not an enum value
    cache.store[key] = json.dumps(entry)

    res = parse_resume(pdf_bytes, gateway=gw, cache=cache)

    assert gw.resume.call_count == 2, "a tampered entry must not be served"
    assert res.source == "llm"
    assert res.prefill["specialization"] == "backend"


def test_cache_works_with_django_cache_signature():
    """BE passes django.core.cache.cache, whose set() calls the ttl `timeout`."""

    class DjangoLikeCache:
        def __init__(self):
            self.store = {}

        def get(self, key, default=None, version=None):
            return self.store.get(key, default)

        def set(self, key, value, timeout=None, version=None):
            self.store[key] = (value, timeout)

    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cache = DjangoLikeCache()
    gw = _gigachat_mock()
    gw.resume.return_value = _llm_draft()

    parse_resume(pdf_bytes, gateway=gw, cache=cache)

    ((value, timeout),) = cache.store.values()
    assert timeout == 7 * 86400
    assert json.loads(value)["source"] == "llm"


def test_prompt_constant_drives_loader_and_cache_key():
    """Renaming the prompt file (a new version) must invalidate the cache (AI-R2)."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cache = InMemoryCache()
    gw = _gigachat_mock()
    gw.resume.return_value = _llm_draft()

    parse_resume(pdf_bytes, gateway=gw, cache=cache)

    redacted_text = redact(extract_text(pdf_bytes)).text
    expected_key = pipeline.cache_key("resume", RESUME_PROMPT, "GigaChat-2", redacted_text)
    assert list(cache.store) == [expected_key]
    assert json.loads(cache.store[expected_key])["prompt"] == RESUME_PROMPT
    assert GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k")).resume_prompt == load_prompt(RESUME_PROMPT)


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

JD_TEXT = (FIXTURES_DIR / "jd" / "jd_backend_must_nice.txt").read_text(encoding="utf-8")


def _install_blueprint(monkeypatch, blueprint_for) -> types.ModuleType:
    module = types.ModuleType("assessment.engine.blueprint")
    module.blueprint_for = blueprint_for
    monkeypatch.setitem(sys.modules, "assessment.engine.blueprint", module)
    return module


def test_blueprint_tuples_are_converted(monkeypatch):
    calls = []

    def blueprint_for(spec, skills):
        calls.append((spec, skills))
        return [("backend.python", 0.6), ("backend.databases", 0.4)]

    _install_blueprint(monkeypatch, blueprint_for)
    res = parse_jd(JD_TEXT, gateway=FakeLlm())

    assert res.blueprint == [
        {"topic": "backend.python", "weight": 0.6},
        {"topic": "backend.databases", "weight": 0.4},
    ]
    assert calls[0][0] == "backend" and "python" in calls[0][1]


def test_blueprint_error_is_logged_with_type_only(monkeypatch, caplog):
    _install_blueprint(monkeypatch, MagicMock(side_effect=ValueError("secret detail")))

    with caplog.at_level(logging.INFO):
        res = parse_jd(JD_TEXT, gateway=FakeLlm())

    assert res.blueprint == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "ValueError" in errors[0].getMessage()
    assert all("secret detail" not in r.getMessage() for r in caplog.records)
    call = next(r for r in caplog.records if getattr(r, "event", None) == "llm_call")
    assert call.fallback_reason == "provider_fake+blueprint"


def test_blueprint_missing_module_is_silent(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "assessment.engine", None)  # import fails with ModuleNotFoundError

    with caplog.at_level(logging.INFO):
        res = parse_jd(JD_TEXT, gateway=FakeLlm())

    assert res.blueprint == []
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_blueprint_not_called_without_specialization(monkeypatch):
    blueprint_for = MagicMock(return_value=[])
    _install_blueprint(monkeypatch, blueprint_for)

    res = parse_jd("Текст без специализации", gateway=FakeLlm())

    assert res.draft["specialization"] == ""
    blueprint_for.assert_not_called()


LLM_CALL_FIELDS = (
    "kind", "provider", "model", "prompt", "input_hash", "latency_ms", "cache_hit", "source",
    "fallback_reason",
)


def test_observability_one_record_no_text_no_pii(caplog):
    """AI-R12: one llm_call record with every field; no CV line and no PII in any record."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    cv_lines = [line.strip() for line in extract_text(pdf_bytes).splitlines() if len(line.strip()) >= 12]
    gw = _gigachat_mock()
    gw.resume.return_value = _llm_draft(about="Опытный бэкенд разработчик на Python.")

    with caplog.at_level(logging.DEBUG):
        res = parse_resume(pdf_bytes, gateway=gw)

    calls = [r for r in caplog.records if getattr(r, "event", None) == "llm_call"]
    assert len(calls) == 1
    for field in LLM_CALL_FIELDS:
        assert hasattr(calls[0], field), field
    assert (calls[0].kind, calls[0].source, calls[0].prompt) == ("resume", "llm", RESUME_PROMPT)

    pii = [v for v in res.contacts.values() if v]
    assert len(pii) == 4
    for record in caplog.records:
        logged = record.getMessage() + " " + " ".join(str(getattr(record, f, "")) for f in LLM_CALL_FIELDS)
        for value in pii + cv_lines:
            assert value not in logged, f"{value!r} leaked into a log record"


def test_get_gateway_factory():
    gw_fake = get_gateway(GatewayConfig(provider="fake"))
    assert gw_fake.name == "fake"

    # GigaChat with dummy key
    gw_giga = get_gateway(GatewayConfig(provider="gigachat", auth_key="dummy-key"))
    assert gw_giga.name == "gigachat"


def test_get_gateway_reads_settings_then_env_and_caches_the_client(settings, monkeypatch):
    """Django settings win (config/settings.py defines LLM_PROVIDER); env fills the rest."""
    settings.LLM_PROVIDER = "gigachat"
    settings.LLM_TIMEOUT_S = "7.5"
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "env-key")
    monkeypatch.setenv("GIGACHAT_MODEL", "GigaChat-2-Pro")

    first, second = get_gateway(), get_gateway()

    assert first is second
    assert (first.name, first.config.model, first.config.timeout_s) == ("gigachat", "GigaChat-2-Pro", 7.5)

    settings.LLM_PROVIDER = "fake"
    assert get_gateway().name == "fake"
