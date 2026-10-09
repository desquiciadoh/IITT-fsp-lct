"""Unit tests for PII redaction and 152-FZ compliance (AI-R1)."""
from pathlib import Path
from unittest.mock import MagicMock

import yaml
from llm_gateway.pdf_text import extract_text
from llm_gateway.redact import assert_clean, redact
from llm_gateway.resume import parse_resume

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


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


def test_redact_empty():
    redacted = redact("")
    assert redacted.text == ""
    assert redacted.found["email"] == []
    assert redacted.found["phone"] == []


def test_pii_cases_fixture():
    """Verify all >= 30 test cases from fixtures/pii_cases.yaml."""
    cases_path = FIXTURES_DIR / "pii_cases.yaml"
    assert cases_path.exists(), "pii_cases.yaml must exist"

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)

    assert len(cases) >= 30, f"Expected at least 30 cases, found {len(cases)}"

    for case in cases:
        c_name = case.get("name", "unnamed")
        raw = case["raw"]
        redacted = redact(raw)

        # Check forbidden substrings are NOT in redacted.text
        for forbidden in case.get("forbidden", []):
            assert forbidden.lower() not in redacted.text.lower(), (
                f"Case '{c_name}': forbidden PII '{forbidden}' leaked into redacted text:\n{redacted.text}"
            )

        # Check negative controls (must preserve)
        for pres in case.get("must_preserve", []):
            assert pres in redacted.text, (
                f"Case '{c_name}': negative control '{pres}' was incorrectly masked:\n{redacted.text}"
            )

        # Check that contacts dict does not contain code annotations
        if "telegram" in redacted.found:
            for tg in redacted.found["telegram"]:
                assert tg not in ("@dataclass", "@pytest", "@property", "@staticmethod"), (
                    f"Case '{c_name}': code annotation {tg} leaked into contacts.telegram"
                )


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

        pdf_bytes = pdf_path.read_bytes()
        text = extract_text(pdf_bytes)
        assert len(text) > 100, f"Expected extracted text from {pdf_name}"

        redacted = redact(text)
        is_clean, residue = assert_clean(redacted)
        assert is_clean, f"Hero CV {pdf_name} failed assert_clean: {residue}"

        # Original contacts should be in found
        assert len(redacted.found["name"]) > 0
        assert len(redacted.found["email"]) > 0
        assert len(redacted.found["phone"]) > 0

        # And zero of found items in text
        for name in redacted.found["name"]:
            for token in name.split():
                if len(token) > 3:
                    assert token.lower() not in redacted.text.lower()


def test_assert_clean_blocks_llm_call():
    """Test that assert_clean blocks the LLM call if unmasked PII was found."""
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"

    # Craft text where monkeypatched or abnormal unmasked PII remains in found
    # We test that parse_resume falls back to rules if assert_clean reports residue
    import io

    # Create dummy PDF bytes
    from fpdf import FPDF
    from llm_gateway.redact import Redacted
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(0, 10, "Test developer resume")
    buf = io.BytesIO()
    pdf.output(buf)
    pdf_bytes = buf.getvalue()

    # Monkeypatch redact to simulate unmasked PII slipping through
    import llm_gateway.resume
    orig_redact = llm_gateway.resume.redact

    try:
        def leaking_redact(text):
            _ = orig_redact(text)
            # Simulate a name that leaked without being replaced
            return Redacted(text="Иванов Иван still in text", found={"name": ["Иванов Иван"]})

        llm_gateway.resume.redact = leaking_redact

        res = parse_resume(pdf_bytes, gateway=mock_gw)

        assert res.source == "rules"
        assert res.fallback_reason == "pii_residual"
        # Verify the mock gateway was NEVER called
        mock_gw.resume.assert_not_called()
    finally:
        llm_gateway.resume.redact = orig_redact
