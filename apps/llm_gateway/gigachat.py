"""GigaChat LLM Gateway adapter.

Implements LlmGateway protocol for Sber GigaChat API:
- Thread-safe OAuth token caching and auto-refresh (~30 min lifetime)
- Timeout budget management per call (LLM_TIMEOUT_S)
- Dynamic header construction on each attempt (handles 401 refresh seamlessly)
- Selective retry (timeouts, 5xx, 429 with Retry-After; never retries 400, 403, 422)
- One automatic repair attempt on malformed JSON
- Strict schema validation via schema.py
- Raises LlmUnavailable / LlmSchemaError with explicit .reason (never swallows errors)
"""
from __future__ import annotations

import http.client
import json
import logging
import math
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .base import (
    JD_PROMPT,
    PHRASE_PROMPT,
    RESUME_PROMPT,
    GatewayConfig,
    LlmSchemaError,
    LlmUnavailable,
    load_prompt,
)
from .schema import validate_jd_payload, validate_resume_payload
from .types import JdDraft, ResumeDraft

logger = logging.getLogger(__name__)

def _is_timeout(error: BaseException) -> bool:
    """socket.timeout / TimeoutError, raw or wrapped in URLError."""
    reason = getattr(error, "reason", None)
    return isinstance(error, TimeoutError) or isinstance(reason, TimeoutError) or "timed out" in str(error).lower()


def _is_tls_verification(error: BaseException) -> bool:
    reason = getattr(error, "reason", None)
    return isinstance(error, ssl.SSLCertVerificationError) or isinstance(reason, ssl.SSLCertVerificationError)


def _retry_after_s(header: str | None) -> float:
    """Retry-After in seconds, clamped to [0, 2]; 0.5 if missing or not a number."""
    try:
        value = float(header) if header else 0.5
    except ValueError:
        return 0.5
    return min(max(value, 0.0), 2.0) if math.isfinite(value) else 0.5


_MAX_BODY_BYTES = 2_000_000


def _read_within(resp: Any, deadline: float) -> bytes:
    """Read the body in chunks; each read waits at most for the budget left (a slow drip of bytes
    cannot outlive the call deadline, which a single read() with a per-socket timeout allows)."""
    chunks: list[bytes] = []
    size = 0
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise LlmUnavailable("Timeout budget exceeded while reading the answer", reason="timeout")
        # http.client drops fp and closes the socket once the body is complete: look it up each time
        sock = getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None)
        if sock is not None:
            try:
                sock.settimeout(left)
            except OSError:
                pass
        chunk = resp.read1(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > _MAX_BODY_BYTES:
            raise LlmUnavailable("GigaChat answer is too large", reason="http_error")


_FENCED_RE = re.compile(r"^\s*`{1,3}[a-zA-Z]*\s*(.*?)\s*`{1,3}\s*$", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the JSON object in a model answer: bare, in a ``` fence, or wrapped in prose.

    Raises ValueError (json.JSONDecodeError included) if there is no JSON object.
    """
    cleaned = text.strip()
    fenced = _FENCED_RE.match(cleaned)
    if fenced:
        cleaned = fenced.group(1)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


class GigaChatLlm:
    """Production GigaChat gateway client with robust error handling and token caching."""

    name: str = "gigachat"

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    COMPLETIONS_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

        # Same constants as the cache keys; a missing prompt file fails here, at construction
        self.resume_prompt = load_prompt(RESUME_PROMPT)
        self.jd_prompt = load_prompt(JD_PROMPT)
        self.phrase_prompt = load_prompt(PHRASE_PROMPT)

        # Setup SSL context (fail-fast if configured bundle path does not exist)
        self._ssl_context = self._build_ssl_context()

    def _build_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with verified CA bundle."""
        if self.config.ca_bundle:
            bundle_p = Path(self.config.ca_bundle)
            if not bundle_p.exists():
                raise FileNotFoundError(f"Configured GIGACHAT_CA_BUNDLE does not exist: {self.config.ca_bundle}")
            return ssl.create_default_context(cafile=str(bundle_p.resolve()))

        # Check default bundled certificate
        default_bundle = Path(__file__).resolve().parent.parent.parent / "certs" / "russian_trusted_ca_bundle.pem"
        if default_bundle.exists():
            return ssl.create_default_context(cafile=str(default_bundle))

        return ssl.create_default_context()

    def _get_access_token(self, deadline: float) -> str:
        """Get cached OAuth token or fetch a new one under lock."""
        with self._token_lock:
            # Refresh 60 seconds before expiry
            if self._access_token and time.time() < (self._token_expires_at - 60):
                return self._access_token

            if not self.config.auth_key:
                raise LlmUnavailable("GIGACHAT_AUTH_KEY is not configured", reason="no_key")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LlmUnavailable("Timeout budget exceeded before OAuth", reason="timeout")

            rquid = str(uuid.uuid4())
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rquid,
                "Authorization": f"Basic {self.config.auth_key}",
            }
            body = urllib.parse.urlencode({"scope": self.config.scope}).encode("utf-8")
            req = urllib.request.Request(self.OAUTH_URL, data=body, headers=headers, method="POST")

            try:
                call_timeout = min(remaining, 8.0)
                with urllib.request.urlopen(req, timeout=call_timeout, context=self._ssl_context) as resp:
                    data = json.loads(_read_within(resp, deadline).decode("utf-8"))
                    self._access_token = data["access_token"]
                    expires_at_raw = data.get("expires_at", (time.time() + 1800) * 1000)
                    self._token_expires_at = (
                        expires_at_raw / 1000.0 if expires_at_raw > 1e11 else float(expires_at_raw)
                    )
                    return self._access_token
            except LlmUnavailable:
                raise
            except urllib.error.HTTPError as e:
                status = e.code
                reason = "no_key" if status in (401, 403) else "http_error"
                raise LlmUnavailable(f"OAuth failed with HTTP {status}", reason=reason) from e
            except Exception as e:
                reason = "timeout" if _is_timeout(e) else "http_error"
                raise LlmUnavailable(f"OAuth request failed: {type(e).__name__}", reason=reason) from e

    def _execute_request(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, deadline: float) -> str:
        """One chat completion within the call deadline (AI-R8).

        401: refresh the token once and retry. Timeouts, network errors, 429 and 5xx: one retry
        if the budget allows the pause. Any other 4xx: no retry.
        """
        refreshed_on_401 = False
        transient_retry_left = True

        def retry_after_pause(pause_s: float) -> bool:
            nonlocal transient_retry_left
            if transient_retry_left and deadline - time.monotonic() > pause_s:
                transient_retry_left = False
                time.sleep(pause_s)
                return True
            return False

        while True:
            if deadline - time.monotonic() <= 0:
                raise LlmUnavailable("Timeout budget exceeded", reason="timeout")

            # Obtain token and build fresh headers on EVERY attempt; the budget left is measured
            # after OAuth, which may have used part of it
            token = self._get_access_token(deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LlmUnavailable("Timeout budget exceeded after OAuth", reason="timeout")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            payload = {
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.COMPLETIONS_URL, data=data, headers=headers, method="POST")

            try:
                call_timeout = min(remaining, 8.0)
                with urllib.request.urlopen(req, timeout=call_timeout, context=self._ssl_context) as resp:
                    body = _read_within(resp, deadline)
                resp_data = json.loads(body.decode("utf-8"))
                content = resp_data["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LlmSchemaError("GigaChat answer has no text content", reason="schema")
                return content

            except (LlmSchemaError, LlmUnavailable):
                raise

            except urllib.error.HTTPError as e:
                status = e.code
                if status == 401 and not refreshed_on_401:
                    # Token invalid/expired - clear token and retry once with fresh token
                    with self._token_lock:
                        self._access_token = None
                    refreshed_on_401 = True
                    continue

                if status == 429:
                    if retry_after_pause(_retry_after_s(e.headers.get("Retry-After") if e.headers else None)):
                        continue
                    raise LlmUnavailable("GigaChat rate limit (429)", reason="http_error") from e

                if status >= 500 and retry_after_pause(0.5):
                    continue

                # 5xx after the retry, 400, 403, 422 and other client errors
                raise LlmUnavailable(f"GigaChat HTTP {status}", reason="http_error") from e

            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                # timeouts, refused/reset connections, RemoteDisconnected, IncompleteRead;
                # a failed certificate check is configuration, not a transient error
                if not _is_tls_verification(e) and retry_after_pause(0.5):
                    continue
                reason = "timeout" if _is_timeout(e) else "http_error"
                raise LlmUnavailable(f"Connection failure: {type(e).__name__}", reason=reason) from e

            except Exception as e:  # a malformed body: not JSON, no "choices"
                raise LlmUnavailable(f"Unexpected response: {type(e).__name__}", reason="http_error") from e

    def _clean_and_parse_json(self, raw_content: str, messages: list[dict[str, str]], deadline: float) -> dict[str, Any]:
        """Parse the model's JSON object; one repair call if it is not one (AI-R3)."""
        try:
            return extract_json_object(raw_content)
        except ValueError as first_err:  # json.JSONDecodeError is a ValueError
            logger.warning("GigaChat answer is not a JSON object (%s), one repair call", type(first_err).__name__)
            if deadline - time.monotonic() <= 1.0:
                raise LlmSchemaError("Malformed JSON and no budget for repair", reason="schema") from first_err

            repair_messages = list(messages) + [
                {"role": "assistant", "content": raw_content},
                {
                    "role": "user",
                    "content": f"Твой ответ не является валидным JSON: {first_err}. Верни ТОЛЬКО исправленный JSON-объект по схеме без комментариев.",
                },
            ]
            repair_content = self._execute_request(repair_messages, temperature=0.0, max_tokens=1500, deadline=deadline)
            try:
                return extract_json_object(repair_content)
            except ValueError as repair_err:
                raise LlmSchemaError("Malformed JSON after the repair call", reason="schema") from repair_err

    def resume(self, redacted_text: str) -> ResumeDraft:
        """Extract structured resume draft via GigaChat.

        Raises:
            LlmUnavailable: on network, auth, timeout, or provider failure.
            LlmSchemaError: on malformed JSON or unparseable schema.
        """
        deadline = time.monotonic() + self.config.timeout_s
        messages = [
            {"role": "system", "content": self.resume_prompt},
            {"role": "user", "content": f"Текст резюме:\n\n{redacted_text}"},
        ]
        content = self._execute_request(messages, temperature=0.1, max_tokens=1500, deadline=deadline)
        parsed_dict = self._clean_and_parse_json(content, messages, deadline)
        return validate_resume_payload(parsed_dict)

    def jd(self, text: str) -> JdDraft:
        """Extract structured JD draft via GigaChat.

        Raises:
            LlmUnavailable: on network, auth, timeout, or provider failure.
            LlmSchemaError: on malformed JSON or unparseable schema.
        """
        deadline = time.monotonic() + self.config.timeout_s
        messages = [
            {"role": "system", "content": self.jd_prompt},
            {"role": "user", "content": f"Текст вакансии:\n\n{text}"},
        ]
        content = self._execute_request(messages, temperature=0.1, max_tokens=1500, deadline=deadline)
        parsed_dict = self._clean_and_parse_json(content, messages, deadline)
        return validate_jd_payload(parsed_dict)

    def phrase(self, facts: list[str]) -> str:
        """Generate short Russian phrasing sentence from facts.

        Raises:
            LlmUnavailable: on network, auth, timeout, or provider failure.
        """
        deadline = time.monotonic() + self.config.timeout_s
        messages = [
            {"role": "system", "content": self.phrase_prompt},
            {"role": "user", "content": "Факты:\n" + "\n".join(f"- {f}" for f in facts)},
        ]
        content = self._execute_request(messages, temperature=0.2, max_tokens=200, deadline=deadline)
        return content.strip()
