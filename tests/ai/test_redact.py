"""Unit tests for PII redaction (152-FZ compliance)."""
from apps.llm_gateway.redact import redact


def test_redact_contacts():
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
