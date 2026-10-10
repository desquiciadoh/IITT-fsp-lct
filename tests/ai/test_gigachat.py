"""Unit tests for GigaChat LLM adapter (AI-R2, AI-R3, AI-R8)."""
import http.client
import io
import json
import ssl
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from llm_gateway.base import GatewayConfig, LlmSchemaError, LlmUnavailable
from llm_gateway.gigachat import GigaChatLlm

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gigachat"


def _expires_in_30_min() -> int:
    """GigaChat returns expires_at in milliseconds; keep it relative so tests never expire."""
    return int((time.time() + 1800) * 1000)


def _completion(content: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        code=code, msg=str(code), hdrs=headers or {}, fp=io.BytesIO(b""),  # type: ignore[arg-type]
    )


class FakeClock:
    """time.monotonic/time.sleep replacement; urlopen advances it by its timeout on a timeout."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


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


@pytest.mark.parametrize(
    ("fixture", "spec", "salary_min"),
    [
        ("valid_resume.json", "backend", 220000),
        ("markdown_fenced.txt", "backend", 220000),
        ("prose_wrapped.txt", "frontend", 90000),
        ("string_salaries_inverted.json", "frontend", 150000),
        ("invalid_enums.json", "backend", 200000),
    ],
)
def test_gigachat_recorded_answers_parse_without_repair(fixture, spec, salary_min):
    """Bare, fenced and prose-wrapped answers parse on the first try; values are normalised."""
    content = (FIXTURES_DIR / fixture).read_text(encoding="utf-8")
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="fake-key"))

    with patch.object(client, "_execute_request", return_value=content) as mock_exec:
        draft = client.resume("[NAME] dev")

    assert mock_exec.call_count == 1
    assert draft.specialization == spec
    assert draft.salary_min == salary_min
    assert draft.claimed_grade in ("junior", "middle", "senior")


def test_gigachat_repair_call_network_failure_keeps_its_reason():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="fake-key"))
    side_effect = ["not json", LlmUnavailable("down", reason="timeout")]

    with patch.object(client, "_execute_request", side_effect=side_effect):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.resume("[NAME] dev")
    assert exc_info.value.reason == "timeout"


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

    oauth_resp_1 = {"access_token": "token-1", "expires_at": _expires_in_30_min()}
    oauth_resp_2 = {"access_token": "token-2", "expires_at": _expires_in_30_min()}
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

    oauth_resp = {"access_token": "token-1", "expires_at": _expires_in_30_min()}
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
    oauth_resp = {"access_token": "cached-token", "expires_at": _expires_in_30_min()}
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


VALID_JD = {
    "title": "Python Developer", "specialization": "backend", "grades": ["middle"],
    "must_skills_raw": ["Python"], "nice_skills_raw": [], "work_formats": ["remote"],
    "location": None, "salary_min": 200000, "salary_max": 300000, "salary_type": "net",
    "team_context": None, "description": None,
}


def _transport(completions: list, calls: dict):
    """urlopen stand-in: OAuth always succeeds; completions are served or raised in order."""

    def fake_urlopen(req, timeout, context):
        if "oauth" in req.full_url:
            calls["oauth"] += 1
            return _make_http_response(200, {"access_token": "t", "expires_at": _expires_in_30_min()})
        calls["chat"] += 1
        item = completions.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _make_http_response(200, item)

    return fake_urlopen


@pytest.mark.parametrize(
    ("errors", "reason"),
    [
        ([_http_error(500), _http_error(500)], "http_error"),
        ([_http_error(502), _http_error(503)], "http_error"),
        ([TimeoutError("timed out"), TimeoutError("timed out")], "timeout"),
        ([urllib.error.URLError(TimeoutError("timed out")), urllib.error.URLError("refused")], "http_error"),
    ],
)
def test_gigachat_transient_errors_get_one_retry(errors, reason):
    """500, 500 -> LlmUnavailable after exactly two attempts (AI-R8)."""
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}

    with patch("urllib.request.urlopen", side_effect=_transport(list(errors), calls)), \
            patch("llm_gateway.gigachat.time.sleep"):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.jd("vacancy")

    assert calls["chat"] == 2
    assert exc_info.value.reason == reason


def test_gigachat_retry_succeeds_after_one_5xx():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}

    with patch("urllib.request.urlopen", side_effect=_transport([_http_error(500), _completion(VALID_JD)], calls)), \
            patch("llm_gateway.gigachat.time.sleep"):
        draft = client.jd("vacancy")

    assert draft.title == "Python Developer"
    assert calls["chat"] == 2


def test_gigachat_429_honours_retry_after_up_to_2s():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}
    completions = [_http_error(429, {"Retry-After": "30"}), _completion(VALID_JD)]

    with patch("urllib.request.urlopen", side_effect=_transport(completions, calls)), \
            patch("llm_gateway.gigachat.time.sleep") as sleep:
        client.jd("vacancy")

    sleep.assert_called_once_with(2.0)


def test_gigachat_timeout_budget_is_respected():
    """OAuth + completion + retry + repair all fit in LLM_TIMEOUT_S, measured on a fake clock."""
    clock = FakeClock()
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k", timeout_s=10.0))
    timeouts: list[float] = []

    def slow_urlopen(req, timeout, context):
        timeouts.append(timeout)
        if "oauth" in req.full_url:
            clock.now += 1.5
            return _make_http_response(200, {"access_token": "t", "expires_at": _expires_in_30_min()})
        clock.now += timeout  # the server never answers
        raise TimeoutError("timed out")

    started = clock.now
    with patch("urllib.request.urlopen", side_effect=slow_urlopen), \
            patch("llm_gateway.gigachat.time.monotonic", clock.monotonic), \
            patch("llm_gateway.gigachat.time.sleep", clock.sleep):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.jd("vacancy")

    assert exc_info.value.reason == "timeout"
    assert clock.now - started <= 10.0
    assert all(t <= 8.0 for t in timeouts)


def test_gigachat_oauth_timeout_reason():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError("timed out"))):
        with pytest.raises(LlmUnavailable) as exc_info:
            client.jd("vacancy")
    assert exc_info.value.reason == "timeout"


def test_gigachat_budget_is_measured_after_oauth():
    """A slow OAuth leaves less time for the completion: the total still fits the budget."""
    clock = FakeClock()
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k", timeout_s=10.0))
    completion_timeouts: list[float] = []

    def slow_oauth_then_hang(req, timeout, context):
        if "oauth" in req.full_url:
            clock.now += 7.9
            return _make_http_response(200, {"access_token": "t", "expires_at": _expires_in_30_min()})
        completion_timeouts.append(timeout)
        clock.now += timeout
        raise TimeoutError("timed out")

    started = clock.now
    with patch("urllib.request.urlopen", side_effect=slow_oauth_then_hang), \
            patch("llm_gateway.gigachat.time.monotonic", clock.monotonic), \
            patch("llm_gateway.gigachat.time.sleep", clock.sleep):
        with pytest.raises(LlmUnavailable):
            client.jd("vacancy")

    assert completion_timeouts[0] <= 2.1 + 1e-9
    assert clock.now - started <= 10.0 + 1e-9


@pytest.mark.parametrize(
    "first_error",
    [
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        http.client.IncompleteRead(b"{\"choi"),
        ConnectionResetError(10054, "reset by peer"),
    ],
)
def test_gigachat_dropped_connections_get_the_retry(first_error):
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}

    with patch("urllib.request.urlopen", side_effect=_transport([first_error, _completion(VALID_JD)], calls)), \
            patch("llm_gateway.gigachat.time.sleep"):
        assert client.jd("vacancy").title == "Python Developer"
    assert calls["chat"] == 2


def test_gigachat_tls_verification_failure_is_not_retried():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}
    tls_error = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))

    with patch("urllib.request.urlopen", side_effect=_transport([tls_error, _completion(VALID_JD)], calls)):
        with pytest.raises(LlmUnavailable):
            client.jd("vacancy")
    assert calls["chat"] == 1


def test_gigachat_negative_retry_after_is_clamped():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}
    completions = [_http_error(429, {"Retry-After": "-1"}), _completion(VALID_JD)]

    with patch("urllib.request.urlopen", side_effect=_transport(completions, calls)), \
            patch("llm_gateway.gigachat.time.sleep") as sleep:
        client.jd("vacancy")
    sleep.assert_called_once_with(0.0)


def test_gigachat_null_content_is_a_schema_error():
    client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k"))
    calls = {"oauth": 0, "chat": 0}
    null_content = {"choices": [{"message": {"content": None}}]}

    with patch("urllib.request.urlopen", side_effect=_transport([null_content], calls)):
        with pytest.raises(LlmSchemaError) as exc_info:
            client.jd("vacancy")
    assert exc_info.value.reason == "schema"


def test_gigachat_slow_drip_body_cannot_outlive_the_budget():
    """A real local server sends the body 4 bytes every 0.3 s: the call stops at the deadline."""
    body = json.dumps(_completion(VALID_JD)).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if "oauth" in self.path:
                payload = json.dumps({"access_token": "t", "expires_at": _expires_in_30_min()}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for i in range(0, len(body), 4):
                    self.wfile.write(body[i:i + 4])
                    self.wfile.flush()
                    time.sleep(0.3)
            except OSError:
                pass  # the client gave up

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        client = GigaChatLlm(GatewayConfig(provider="gigachat", auth_key="k", timeout_s=2.0))
        client.OAUTH_URL = f"{base}/oauth"
        client.COMPLETIONS_URL = f"{base}/chat/completions"
        started = time.monotonic()
        with pytest.raises(LlmUnavailable) as exc_info:
            client.jd("vacancy")
        elapsed = time.monotonic() - started
    finally:
        server.shutdown()
        server.server_close()

    assert exc_info.value.reason == "timeout"
    assert elapsed < 3.5, f"took {elapsed:.1f}s with a 2 s budget"


def test_two_parse_calls_share_one_oauth_token():
    """get_gateway() caches the client per config, so the second parse reuses the token."""
    from llm_gateway import get_gateway, parse_jd

    config = GatewayConfig(provider="gigachat", auth_key="shared-key-for-this-test")
    calls = {"oauth": 0, "chat": 0}
    completions = [_completion(VALID_JD), _completion({**VALID_JD, "title": "Go Developer"})]

    with patch("urllib.request.urlopen", side_effect=_transport(completions, calls)):
        first = parse_jd("Python developer, зарплата 200 000 - 300 000 руб", gateway=get_gateway(config))
        second = parse_jd("Go developer, зарплата 200 000 - 300 000 руб", gateway=get_gateway(config))

    assert (first.source, second.source) == ("llm", "llm")
    assert calls == {"oauth": 1, "chat": 2}
