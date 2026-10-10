"""Unit tests for PII redaction and 152-FZ compliance (AI-R1)."""
from pathlib import Path
from unittest.mock import MagicMock

import llm_gateway.resume
import pytest
import yaml
from llm_gateway.pdf_text import extract_text
from llm_gateway.redact import assert_clean, redact
from llm_gateway.resume import parse_resume
from llm_gateway.types import Redacted

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PII_CASES = yaml.safe_load((FIXTURES_DIR / "pii_cases.yaml").read_text(encoding="utf-8"))
FOUND_KEYS = {
    "expected_name": "name",
    "expected_tg": "telegram",
    "expected_email": "email",
    "expected_phone": "phone",
    "expected_url": "url",
}


def test_redact_contacts_basic():
    raw_cv = """Иванов Иван Иванович
Email: ivan.developer@example.com
Телефон: +7 (999) 123-45-67, дополнительный 8-916-777-88-99
Telegram: @ivan_code или https://t.me/ivan_alt
GitHub: https://github.com/ivan-dev
Опыт работы: 4 года Python backend разработки в финтехе.
Стек: Python, Django, PostgreSQL, Docker, Redis.
"""
    redacted = redact(raw_cv)

    # Verify sensitive data was extracted into found dict
    assert "ivan.developer@example.com" in redacted.found["email"]
    assert any("999" in p for p in redacted.found["phone"])
    assert "@ivan_code" in redacted.found["telegram"] or "@ivan_alt" in redacted.found["telegram"]
    assert any("github.com" in u for u in redacted.found["url"])
    assert any("Иванов" in n for n in redacted.found["name"])
    assert redacted.full_name == "Иванов Иван Иванович"

    # Crucial 152-FZ check: original PII must NOT be present in redacted.text
    assert "ivan.developer@example.com" not in redacted.text
    assert "123-45-67" not in redacted.text
    assert "777-88-99" not in redacted.text
    assert "Иванов Иван Иванович" not in redacted.text
    assert "@ivan_code" not in redacted.text

    # Placeholders must be present
    assert "[EMAIL]" in redacted.text
    assert "[PHONE]" in redacted.text
    assert "[TG]" in redacted.text
    assert "[URL]" in redacted.text
    assert "[NAME]" in redacted.text

    # Technical content should remain intact
    assert "Python, Django, PostgreSQL, Docker, Redis" in redacted.text
    assert assert_clean(redacted) == (True, None)


def test_redact_empty():
    redacted = redact("")
    assert redacted.text == ""
    assert redacted.found["email"] == []
    assert redacted.found["phone"] == []
    assert redacted.full_name is None


def test_pii_cases_fixture_size():
    assert len(PII_CASES) >= 30, f"Expected at least 30 cases, found {len(PII_CASES)}"


@pytest.mark.parametrize("case", PII_CASES, ids=[c["name"] for c in PII_CASES])
def test_pii_case(case):
    """Each case: expected `found` values, no original PII in the text, negatives preserved."""
    redacted = redact(case["raw"])

    for key, kind in FOUND_KEYS.items():
        if key not in case:
            continue
        if case[key] is None:
            assert redacted.found[kind] == [], f"unexpected {kind}: {redacted.found[kind]}"
        else:
            assert case[key] in redacted.found[kind], f"{case[key]!r} not in {redacted.found[kind]}"
    for url in case.get("expected_urls", []):
        assert url in redacted.found["url"]
    if "expected_full_name" in case:
        assert redacted.full_name == case["expected_full_name"]

    for forbidden in case.get("forbidden", []):
        assert forbidden.lower() not in redacted.text.lower(), (
            f"forbidden PII {forbidden!r} leaked into redacted text:\n{redacted.text}"
        )
    for kept in case.get("must_preserve", []):
        assert kept in redacted.text, f"{kept!r} was masked:\n{redacted.text}"

    assert assert_clean(redacted) == (True, None)


def test_header_names_off_for_job_descriptions():
    """parse_jd turns the header heuristic off: a company in the title is not a person."""
    redacted = redact("Альфа Банк Ромашка\nPython разработчик", header_names=False)
    assert redacted.found["name"] == []
    assert "Альфа Банк Ромашка" in redacted.text


def test_hero_cvs_zero_leaks():
    """Verify that all 3 hero CV PDFs pass redaction with zero PII leaks."""
    hero_pdfs = [
        "cv_backend_middle.pdf",
        "cv_frontend_junior.pdf",
        "cv_ml_senior.pdf",
    ]
    cv_dir = FIXTURES_DIR / "cv"

    for pdf_name in hero_pdfs:
        pdf_path = cv_dir / pdf_name
        assert pdf_path.exists(), f"Hero PDF {pdf_name} must exist"

        text = extract_text(pdf_path.read_bytes())
        assert len(text) > 100, f"Expected extracted text from {pdf_name}"

        redacted = redact(text)
        assert assert_clean(redacted) == (True, None), f"Hero CV {pdf_name} failed assert_clean"

        # Original contacts should be in found
        assert redacted.full_name
        assert len(redacted.found["email"]) > 0
        assert len(redacted.found["phone"]) > 0
        assert len(redacted.found["telegram"]) > 0

        # And none of the found values is left in the text
        for kind, values in redacted.found.items():
            for value in values:
                for token in value.lstrip("@").split():
                    if len(token) > 3:
                        assert token.lower() not in redacted.text.lower(), f"{kind} {token!r} leaked"


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Связь: ivan@example.com", {}),
        ("Телефон 8 916 123 45 67", {}),
        ("Сайт https://ivanov.dev", {}),
        ("Портфолио ivanov.dev/projects", {}),
        ("Telegram: @ivan_petrov", {}),
        ("Пишите @ivan_petrov", {}),
        ("Иванов Иван любит Python", {"name": ["Иванов Иван"]}),
        ("Профиль: ivan_petrov_42", {"telegram": ["@ivan_petrov_42"]}),
    ],
)
def test_assert_clean_catches_residual_pii(text, found):
    """The safety net re-runs every detector and looks for every found value."""
    full_found = {"email": [], "phone": [], "telegram": [], "url": [], "name": [], **found}
    assert assert_clean(Redacted(text=text, found=full_found)) == (False, "pii_residual")


def test_assert_clean_blocks_llm_call(monkeypatch):
    """If a name slips through redaction, the LLM is never called and rules take over."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"

    def leaking_redact(text, **kwargs):
        return Redacted(
            text="Иванов Иван still in text",
            found={"email": [], "phone": [], "telegram": [], "url": [], "name": ["Иванов Иван"]},
            full_name="Иванов Иван",
        )

    monkeypatch.setattr(llm_gateway.resume, "redact", leaking_redact)
    res = parse_resume(pdf_bytes, gateway=mock_gw)

    assert res.source == "rules"
    assert res.fallback_reason == "pii_residual"
    mock_gw.resume.assert_not_called()


def test_residual_pii_never_reaches_profile_free_text(monkeypatch):
    """A phone the redactor missed must not be copied into about/experience_text."""
    pdf_bytes = (FIXTURES_DIR / "cv" / "cv_backend_middle.pdf").read_bytes()
    leaked = "Обо мне:\nЗвоните 8-999-1234567 в любое время.\nОпыт работы:\nООО Ромашка, звонить 8-999-1234567"

    def leaking_redact(text, **kwargs):
        return Redacted(text=leaked, found={"email": [], "phone": [], "telegram": [], "url": [], "name": []})

    monkeypatch.setattr(llm_gateway.resume, "redact", leaking_redact)
    gateway = MagicMock()
    gateway.name = "gigachat"
    res = parse_resume(pdf_bytes, gateway=gateway)

    gateway.resume.assert_not_called()
    assert res.fallback_reason == "pii_residual"
    assert res.prefill["about"] == "" and res.prefill["experience_text"] == ""
    assert "1234567" not in str(res.prefill)
