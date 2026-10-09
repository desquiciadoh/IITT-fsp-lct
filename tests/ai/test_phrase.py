"""Unit tests for phrase generation and AI-R9 grounding checks."""
import logging
from unittest.mock import MagicMock

from llm_gateway.base import LlmUnavailable
from llm_gateway.phrase import phrase


def test_phrase_rejects_hallucinated_skills():
    facts = ["Python 4 года", "PostgreSQL опыт 3 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    # Model introduces Rust and Kubernetes which are not in facts
    mock_gw.phrase.return_value = "Кандидат отлично знает Rust и Kubernetes на высоком уровне."

    res = phrase(facts, gateway=mock_gw)
    # Must reject and fall back to template containing facts
    assert "Rust" not in res
    assert "Kubernetes" not in res
    assert "Python" in res


def test_phrase_rejects_hallucinated_numbers():
    facts = ["Опыт работы 3 года", "Решено 10 задач"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    # Model invents 5 years instead of 3
    mock_gw.phrase.return_value = "Кандидат имеет опыт работы 5 лет и решил 10 задач."

    res = phrase(facts, gateway=mock_gw)
    # Must reject and fall back to template
    assert "5" not in res
    assert "3 года" in res or "10" in res


def test_phrase_accepts_reformatted_numbers():
    facts = ["Ожидания по зарплате 250 000 руб"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    # Reformatted 250 000 -> 250000 should be accepted
    mock_gw.phrase.return_value = "Зарплатные ожидания кандидата составляют 250000 руб."

    res = phrase(facts, gateway=mock_gw)
    assert res == "Зарплатные ожидания кандидата составляют 250000 руб."


def test_phrase_rejects_three_sentences():
    facts = ["Python 3 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.return_value = "Первое предложение. Второе предложение. Третье предложение."

    res = phrase(facts, gateway=mock_gw)
    assert "Первое предложение" not in res
    assert "Python" in res


def test_phrase_rejects_length_over_300():
    facts = ["Python 3 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.return_value = "Python " + ("очень " * 60) + "разработчик."

    res = phrase(facts, gateway=mock_gw)
    assert len(res) <= 300
    assert "Python" in res


def test_phrase_rejects_pii_placeholders():
    facts = ["Python 3 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.return_value = "Кандидат [NAME] отлично знает Python."

    res = phrase(facts, gateway=mock_gw)
    assert "[NAME]" not in res


def test_phrase_accepts_decimals_and_dotted_names():
    """'4.5 года' and 'Node.js' are not sentence ends: two sentences are accepted."""
    facts = ["Node.js: 4.5 года", "Vue.js: подтверждено тестом"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.return_value = "Кандидат 4.5 года пишет на Node.js. Навык Vue.js подтверждён тестом."

    assert phrase(facts, gateway=mock_gw) == mock_gw.phrase.return_value


def test_phrase_logs_one_structured_record(caplog):
    facts = ["Python 4 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.return_value = "Кандидат знает Python и Rust."

    with caplog.at_level(logging.INFO, logger="llm_gateway"):
        phrase(facts, gateway=mock_gw)

    records = [r for r in caplog.records if getattr(r, "event", None) == "llm_call"]
    assert len(records) == 1
    assert (records[0].kind, records[0].source, records[0].fallback_reason) == ("phrase", "rules", "grounding_skills")
    assert all("Rust" not in r.getMessage() for r in caplog.records), "model output must not be logged"


def test_phrase_fallback_on_gateway_error():
    facts = ["FastAPI 2 года"]
    mock_gw = MagicMock()
    mock_gw.name = "gigachat"
    mock_gw.phrase.side_effect = LlmUnavailable("Network down", reason="http_error")

    res = phrase(facts, gateway=mock_gw)
    assert "FastAPI" in res
