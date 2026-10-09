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

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .base import GatewayConfig, LlmSchemaError, LlmUnavailable
from .schema import validate_jd_payload, validate_resume_payload
from .types import JdDraft, ResumeDraft

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


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

        # Load prompts (using resume.v2.md per AI-R6)
        self.resume_prompt = self._load_prompt("resume.v2.md")
        if not self.resume_prompt:
            self.resume_prompt = self._load_prompt("resume.v1.md")
        self.jd_prompt = self._load_prompt("jd.v1.md")
        self.phrase_prompt = self._load_prompt("phrase.v1.md")

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

    def _load_prompt(self, filename: str) -> str:
        prompt_file = PROMPTS_DIR / filename
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return ""

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
                    data = json.loads(resp.read().decode("utf-8"))
                    self._access_token = data["access_token"]
                    expires_at_raw = data.get("expires_at", (time.time() + 1800) * 1000)
                    self._token_expires_at = (
                        expires_at_raw / 1000.0 if expires_at_raw > 1e11 else float(expires_at_raw)
                    )
                    return self._access_token
            except urllib.error.HTTPError as e:
                status = e.code
                reason = "http_error" if status >= 500 else "no_key" if status in (401, 403) else "http_error"
                raise LlmUnavailable(f"OAuth failed with HTTP {status}", reason=reason) from e
            except Exception as e:
                raise LlmUnavailable(f"OAuth request failed: {e}", reason="http_error") from e

    def _execute_request(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, deadline: float) -> str:
        """Execute chat completion request respecting call deadline and handling retries."""
        refreshed_on_401 = False
        attempt = 0

        while True:
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LlmUnavailable("Timeout budget exceeded", reason="timeout")

            # Obtain token and build fresh headers on EVERY attempt
            token = self._get_access_token(deadline)
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
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    return resp_data["choices"][0]["message"]["content"]

            except urllib.error.HTTPError as e:
                status = e.code
                if status == 401 and not refreshed_on_401:
                    # Token invalid/expired - clear token and retry once with fresh token
                    with self._token_lock:
                        self._access_token = None
                    refreshed_on_401 = True
                    continue

                if status == 429 and attempt <= 2:
                    retry_after = e.headers.get("Retry-After")
                    sleep_s = 0.5
                    if retry_after:
                        try:
                            sleep_s = min(float(retry_after), 2.0)
                        except ValueError:
                            pass
                    if (deadline - time.monotonic()) > sleep_s:
                        time.sleep(sleep_s)
                        continue
                    raise LlmUnavailable("Rate limited (429) and deadline exceeded", reason="http_error") from e

                if status >= 500 and attempt <= 2:
                    if (deadline - time.monotonic()) > 0.5:
                        time.sleep(0.5)
                        continue
                    raise LlmUnavailable(f"GigaChat server error {status}", reason="http_error") from e

                # 400, 403, 422 or other unrecoverable client errors: do not retry
                raise LlmUnavailable(f"GigaChat HTTP {status}", reason="http_error") from e

            except (urllib.error.URLError, TimeoutError) as e:
                if attempt <= 2 and (deadline - time.monotonic()) > 0.5:
                    time.sleep(0.5)
                    continue
                reason = "timeout" if "timed out" in str(e).lower() else "http_error"
                raise LlmUnavailable(f"Connection failure: {e}", reason=reason) from e

            except Exception as e:
                raise LlmUnavailable(f"Unexpected error: {e}", reason="http_error") from e

    def _clean_and_parse_json(self, raw_content: str, messages: list[dict[str, str]], deadline: float) -> dict[str, Any]:
        """Strip markdown fences and parse JSON. Performs 1 repair attempt if malformed."""
        def extract_json(text: str) -> dict[str, Any]:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("JSON root is not an object")
            return parsed

        try:
            return extract_json(raw_content)
        except Exception as first_err:
            logger.warning(f"GigaChat output is not valid JSON ({first_err}), attempting 1 repair call")
            # Repair attempt per AI-R3
            remaining = deadline - time.monotonic()
            if remaining <= 1.0:
                raise LlmSchemaError(f"Malformed JSON and no budget for repair: {first_err}", reason="schema") from first_err

            repair_messages = list(messages) + [
                {"role": "assistant", "content": raw_content},
                {
                    "role": "user",
                    "content": f"Твой ответ не является валидным JSON: {first_err}. Верни ТОЛЬКО исправленный JSON-объект по схеме без комментариев.",
                },
            ]
            try:
                repair_content = self._execute_request(repair_messages, temperature=0.0, max_tokens=1500, deadline=deadline)
                return extract_json(repair_content)
            except Exception as repair_err:
                raise LlmSchemaError(f"Malformed JSON after repair attempt: {repair_err}", reason="schema") from repair_err

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
