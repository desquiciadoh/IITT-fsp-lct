"""Unit tests for GigaChat LLM adapter (AI-R2, AI-R3, AI-R8)."""
import io
import json
import urllib.error
from unittest.mock import patch

import pytest
from llm_gateway.base import GatewayConfig, LlmSchemaError, LlmUnavailable
from llm_gateway.gigachat import GigaChatLlm


def _make_http_response(status: int, body_dict: dict | str) -> io.BytesIO:
    if isinstance(body_dict, dict):
        raw = json.dumps(body_dict).encode("utf-8")
    else:
        raw = body_dict.encode("utf-8")
    resp = io.BytesIO(raw)
    resp.status = status  # type: ignore
    return resp


def test_gigachat_initialization_missing_ca_bundle_raises():
    """Verify AI-R8: missing ca_bundle path raises FileNotFoundError immediately."""
    config = GatewayConfig(
        provider="gigachat",
        auth_key="test-key",
        ca_bundle="non_existent_path_to_bundle.pem",
    )
    with pytest.raises(FileNotFoundError):
        GigaChatLlm(config)


def test_gigachat_resume_raises_llm_unavailable():
    """Verify AI-R2: GigaChatLlm RAISES LlmUnavailable instead of falling back to FakeLlm."""
    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)

    with patch.object(client, "_execute_request", side_effect=LlmUnavailable("Network down", reason="http_error")):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.resume("[NAME] Python dev")
        assert exc_info.value.reason == "http_error"


def test_gigachat_repair_attempt_on_invalid_json():
    """Verify AI-R3: one repair attempt on malformed JSON output."""
    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)

    valid_json_str = """{
        "specialization": "backend",
        "claimed_grade": "middle",
        "years_experience": 3.0,
        "roles": ["Backend Developer"],
        "skills_raw": ["Python"],
        "work_formats": ["remote"],
        "salary_min": 200000,
        "salary_max": 250000,
        "salary_type": "net",
        "city": "Москва",
        "about": null,
        "experience_text": null
    }"""

    # First call returns invalid JSON, second call (repair) returns valid JSON
    with patch.object(client, "_execute_request", side_effect=["Not JSON at all", valid_json_str]) as mock_exec:
        draft = client.resume("[NAME] Python dev")
        assert draft.specialization == "backend"
        assert draft.claimed_grade == "middle"
        assert mock_exec.call_count == 2
        # Verify the second call received the repair message prompt
        repair_messages = mock_exec.call_args_list[1][0][0]
        assert any("исправленный JSON" in m["content"] for m in repair_messages if m["role"] == "user")


def test_gigachat_invalid_json_twice_raises_schema_error():
    """Verify AI-R3: if repair attempt fails too, raises LlmSchemaError(reason='schema')."""
    config = GatewayConfig(provider="gigachat", auth_key="fake-key")
    client = GigaChatLlm(config)

    with patch.object(client, "_execute_request", side_effect=["Bad JSON 1", "Bad JSON 2"]):
        with pytest.raises(LlmSchemaError) as exc_info:
            client.resume("[NAME] Python dev")
        assert exc_info.value.reason == "schema"


def test_gigachat_transport_401_refreshes_token():
    """Verify AI-R8: on 401, refreshes OAuth token and retries with new Authorization header."""
    config = GatewayConfig(provider="gigachat", auth_key="secret-key")
    client = GigaChatLlm(config)

    oauth_resp_1 = {"access_token": "token-1", "expires_at": 1800000000000}
    oauth_resp_2 = {"access_token": "token-2", "expires_at": 1800000000000}
    completion_ok = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "specialization": "backend",
                    "claimed_grade": "senior",
                    "years_experience": 5.0,
                    "roles": ["Lead"],
                    "skills_raw": ["Python"],
                    "work_formats": ["remote"],
                    "salary_min": 300000,
                    "salary_max": 400000,
                    "salary_type": "net",
                    "city": "Москва",
                    "about": None,
                    "experience_text": None,
                })
            }
        }]
    }

    # Simulate sequence of responses:
    # 1. OAuth -> token-1
    # 2. Chat completion -> 401 HTTPError
    # 3. OAuth -> token-2
    # 4. Chat completion -> 200 OK
    fp = io.BytesIO(b"Unauthorized")
    err_401 = urllib.error.HTTPError(
        url="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={},  # type: ignore
        fp=fp,
    )

    call_count = 0
    requested_auth_headers = []

    def fake_urlopen(req, timeout, context):
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "oauth" in url:
            if call_count == 1:
                return _make_http_response(200, oauth_resp_1)
            else:
                return _make_http_response(200, oauth_resp_2)
        elif "chat/completions" in url:
            auth_header = req.headers.get("Authorization")
            requested_auth_headers.append(auth_header)
            if call_count == 2:
                raise err_401
            return _make_http_response(200, completion_ok)
        raise RuntimeError("Unexpected URL")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        draft = client.resume("[NAME] Python Lead")
        assert draft.specialization == "backend"
        assert draft.claimed_grade == "senior"
        # First request used Bearer token-1, retry used Bearer token-2!
        assert requested_auth_headers == ["Bearer token-1", "Bearer token-2"]


def test_gigachat_transport_400_no_retry():
    """Verify AI-R8: 400 client error does not retry and raises LlmUnavailable."""
    config = GatewayConfig(provider="gigachat", auth_key="secret-key")
    client = GigaChatLlm(config)

    oauth_resp = {"access_token": "token-1", "expires_at": 1800000000000}
    fp = io.BytesIO(b"Bad Request")
    err_400 = urllib.error.HTTPError(
        url="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        code=400,
        msg="Bad Request",
        hdrs={},  # type: ignore
        fp=fp,
    )

    completion_attempts = 0

    def fake_urlopen(req, timeout, context):
        nonlocal completion_attempts
        if "oauth" in req.full_url:
            return _make_http_response(200, oauth_resp)
        completion_attempts += 1
        raise err_400

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.resume("[NAME] Python")
        assert exc_info.value.reason == "http_error"
        # Must not retry 400
        assert completion_attempts == 1


def test_gigachat_token_reuse():
    """Verify AI-R8: multiple requests reuse cached token within lifetime."""
    config = GatewayConfig(provider="gigachat", auth_key="secret-key")
    client = GigaChatLlm(config)

    oauth_calls = 0
    oauth_resp = {"access_token": "cached-token", "expires_at": 1800000000000}
    completion_resp = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "specialization": "backend",
                    "claimed_grade": "middle",
                    "years_experience": 3.0,
                    "roles": ["Dev"],
                    "skills_raw": ["Python"],
                    "work_formats": ["remote"],
                    "salary_min": None,
                    "salary_max": None,
                    "salary_type": None,
                    "city": None,
                    "about": None,
                    "experience_text": None,
                })
            }
        }]
    }

    def fake_urlopen(req, timeout, context):
        nonlocal oauth_calls
        if "oauth" in req.full_url:
            oauth_calls += 1
            return _make_http_response(200, oauth_resp)
        return _make_http_response(200, completion_resp)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.resume("CV 1")
        client.resume("CV 2")
        # Token must be fetched only once
        assert oauth_calls == 1
