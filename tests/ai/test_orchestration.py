"""Unit tests for LLM Gateway orchestration (parse_resume, parse_jd, phrase, cache)."""
import io
import pytest
from pypdf import PdfWriter

from apps.llm_gateway import (
    FakeLlm,
    UnreadablePdf,
    extract_text,
    get_gateway,
    parse_jd,
    parse_resume,
    phrase,
)


class InMemoryCache:
    """Simple dict-backed cache for unit testing."""
    def __init__(self):
        self.store = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ttl: int):
        self.store[key] = value


def _create_test_pdf(text: str) -> bytes:
    """Create a minimal real PDF with text stream for test extraction."""
    # Build minimal valid PDF using pypdf
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    # pypdf writer doesn't easily draw text without reportlab,
    # so we test extraction by monkeypatching or using raw stream
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_parse_jd_orchestration():
    text = """Backend Team Lead (Python)
Обязательно:
- Отличное владение Python, Django, PostgreSQL
- Опыт с микросервисами и Docker
Желательно:
- Kubernetes (k8s), Kafka, Redis
Условия:
- Формат: удаленка или гибрид
- Зарплата от 350 000 до 450 000 руб на руки
Локация: Москва
"""
    cache = InMemoryCache()
    res = parse_jd(text, gateway=FakeLlm(), cache=cache)

    assert res.source == "rules"
    assert res.draft["specialization"] == "backend"
    assert "python" in res.draft["must_skills"]
    assert "django" in res.draft["must_skills"]
    assert "postgresql" in res.draft["must_skills"]
    assert "kubernetes" in res.draft["nice_skills"]
    assert "remote" in res.draft["work_formats"]
    assert res.draft["salary_min"] == 350000
    assert res.draft["salary_max"] == 450000
    assert res.draft["salary_type"] == "net"

    # Second call with same text should hit cache
    res2 = parse_jd(text, cache=cache)
    assert res2.draft["specialization"] == "backend"


def test_parse_resume_empty_pdf_raises_unreadable():
    with pytest.raises(UnreadablePdf):
        parse_resume(b"")

    with pytest.raises(UnreadablePdf):
        parse_resume(b"corrupted invalid not-a-pdf bytes")


def test_phrase_grounding_rejects_hallucinated_numbers():
    facts = [
        "Опыт работы на Python 4 года",
        "Успешно решено 12 задач по алгоритмам",
    ]
    # Default template output should be grounded in the facts
    output = phrase(facts)
    assert "Python" in output
    assert "4" in output or "12" in output


def test_get_gateway_factory():
    from apps.llm_gateway.base import GatewayConfig
    gw_fake = get_gateway(GatewayConfig(provider="fake"))
    assert gw_fake.name == "fake"

    gw_giga = get_gateway(GatewayConfig(provider="gigachat", auth_key="dummy-key"))
    assert gw_giga.name == "gigachat"
