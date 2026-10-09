"""Unit tests for GigaChat LLM adapter with mocked network responses."""
from unittest.mock import MagicMock, patch

from apps.llm_gateway.base import GatewayConfig
from apps.llm_gateway.gigachat import GigaChatLlm


def test_gigachat_initialization():
    config = GatewayConfig(
        provider="gigachat",
        auth_key="fake-test-key",
        model="GigaChat-2",
        timeout_s=5.0,
    )
    client = GigaChatLlm(config)
    assert client.name == "gigachat"
    assert "resume.v1.md" in client.resume_prompt or len(client.resume_prompt) > 0


def test_clean_json_output():
    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)

    # Standard JSON string
    res = client._clean_json_output('{"specialization": "backend"}')
    assert res["specialization"] == "backend"

    # JSON wrapped in markdown codeblock
    wrapped = """```json
{
  "specialization": "frontend",
  "salary_min": 150000
}
```"""
    res2 = client._clean_json_output(wrapped)
    assert res2["specialization"] == "frontend"
    assert res2["salary_min"] == 150000


@patch.object(GigaChatLlm, "_chat_completion")
def test_gigachat_resume_success(mock_chat):
    mock_chat.return_value = """{
        "specialization": "backend",
        "claimed_grade": "middle",
        "years_experience": 3.5,
        "roles": ["Backend Developer"],
        "skills_raw": ["Python", "FastAPI", "PostgreSQL"],
        "work_formats": ["remote"],
        "salary_min": 250000,
        "salary_max": null,
        "salary_type": "net",
        "city": "Москва",
        "about": "Backend разработчик",
        "experience_text": "3 года в финтехе"
    }"""

    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)
    draft = client.resume("[NAME] Python dev")

    assert draft.specialization == "backend"
    assert draft.claimed_grade == "middle"
    assert draft.years_experience == 3.5
    assert "FastAPI" in draft.skills_raw
    assert draft.salary_min == 250000


@patch.object(GigaChatLlm, "_chat_completion")
def test_gigachat_fallback_on_error(mock_chat):
    mock_chat.side_effect = Exception("API connection timeout")

    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)

    # Should not raise exception, but gracefully degrade to FakeLlm
    draft = client.resume("[NAME] Python backend developer. Опыт 3 года.")
    assert draft.specialization == "backend"
    assert draft.years_experience == 3.0
