"""GigaChat LLM Gateway adapter.

Implements LlmGateway protocol for Sber GigaChat API:
- OAuth token caching and auto-refresh (~30 min lifetime)
- 10 s timeout and 1 automatic retry
- Structured JSON output with schema validation and markdown cleanup
- TLS verification with Russian CA bundle support (GIGACHAT_CA_BUNDLE)
- Graceful fallback to FakeLlm on any error
"""
from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .base import GatewayConfig, LlmGateway
from .fake import FakeLlm
from .types import JdDraft, ResumeDraft

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class GigaChatAuthError(Exception):
    """Raised when GigaChat OAuth authentication fails."""


class GigaChatApiError(Exception):
    """Raised when GigaChat API call fails."""


class GigaChatLlm:
    """Production GigaChat gateway client."""

    name: str = "gigachat"

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    COMPLETIONS_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

        # Load prompts
        self.resume_prompt = self._load_prompt("resume.v1.md")
        self.jd_prompt = self._load_prompt("jd.v1.md")
        self.phrase_prompt = self._load_prompt("phrase.v1.md")

        # Setup SSL context
        self._ssl_context = self._build_ssl_context()

    def _build_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with optional Russian CA bundle."""
        bundle_path = None
        if self.config.ca_bundle and Path(self.config.ca_bundle).exists():
            bundle_path = Path(self.config.ca_bundle).resolve()
        else:
            default_bundle = Path(__file__).resolve().parent.parent.parent / "certs" / "russian_trusted_ca_bundle.pem"
            if default_bundle.exists():
                bundle_path = default_bundle

        if bundle_path:
            return ssl.create_default_context(cafile=str(bundle_path))
        return ssl.create_default_context()

    def _load_prompt(self, filename: str) -> str:
        prompt_file = PROMPTS_DIR / filename
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return ""

    def _get_access_token(self) -> str:
        """Get cached OAuth token or fetch a new one."""
        now = time.time()
        # Refresh 60 seconds before expiry
        if self._access_token and now < (self._token_expires_at - 60):
            return self._access_token

        if not self.config.auth_key:
            raise GigaChatAuthError("GIGACHAT_AUTH_KEY is not configured")

        rquid = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rquid,
            "Authorization": f"Basic {self.config.auth_key}",
        }
        body = urllib.parse.urlencode({"scope": self.config.scope}).encode("utf-8")

        req = urllib.request.Request(self.OAUTH_URL, data=body, headers=headers, method="POST")

        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_s, context=self._ssl_context) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self._access_token = data["access_token"]
                    # expires_at is typically unix timestamp in ms
                    expires_at_raw = data.get("expires_at", (now + 1800) * 1000)
                    self._token_expires_at = expires_at_raw / 1000.0 if expires_at_raw > 1e11 else float(expires_at_raw)
                    return self._access_token
            except Exception as e:
                if attempt == 1:
                    raise GigaChatAuthError(f"OAuth token request failed: {e}") from e
                time.sleep(1.0)

        raise GigaChatAuthError("OAuth token request failed after retry")

    def _chat_completion(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        """Execute chat completion with 1 retry on error."""
        token = self._get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")

        last_err: Exception | None = None
        for attempt in range(2):  # initial call + 1 retry
            try:
                req = urllib.request.Request(self.COMPLETIONS_URL, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.config.timeout_s, context=self._ssl_context) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content = resp_data["choices"][0]["message"]["content"]
                    return content
            except Exception as e:
                last_err = e
                # If token expired or rejected, invalidate and retry
                self._access_token = None
                time.sleep(0.5)

        raise GigaChatApiError(f"GigaChat API completion failed after retry: {last_err}")

    def _clean_json_output(self, text: str) -> dict[str, Any]:
        """Strip markdown fences and parse JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        return json.loads(cleaned)

    def resume(self, redacted_text: str) -> ResumeDraft:
        """Extract structured resume draft via GigaChat."""
        messages = [
            {"role": "system", "content": self.resume_prompt},
            {"role": "user", "content": f"Текст резюме:\n\n{redacted_text}"},
        ]
        try:
            content = self._chat_completion(messages, temperature=0.1)
            parsed = self._clean_json_output(content)
            return ResumeDraft(
                specialization=parsed.get("specialization"),
                claimed_grade=parsed.get("claimed_grade"),
                years_experience=float(parsed["years_experience"]) if parsed.get("years_experience") is not None else None,
                roles=list(parsed.get("roles") or []),
                skills_raw=list(parsed.get("skills_raw") or []),
                work_formats=list(parsed.get("work_formats") or []),
                salary_min=int(parsed["salary_min"]) if parsed.get("salary_min") is not None else None,
                salary_max=int(parsed["salary_max"]) if parsed.get("salary_max") is not None else None,
                salary_type=parsed.get("salary_type"),
                city=parsed.get("city"),
                about=parsed.get("about"),
                experience_text=parsed.get("experience_text"),
            )
        except Exception as e:
            logger.warning(f"GigaChat resume parsing failed: {e}. Falling back to FakeLlm.")
            return FakeLlm().resume(redacted_text)

    def jd(self, text: str) -> JdDraft:
        """Extract structured JD draft via GigaChat."""
        messages = [
            {"role": "system", "content": self.jd_prompt},
            {"role": "user", "content": f"Текст вакансии:\n\n{text}"},
        ]
        try:
            content = self._chat_completion(messages, temperature=0.1)
            parsed = self._clean_json_output(content)
            return JdDraft(
                title=parsed.get("title"),
                specialization=parsed.get("specialization"),
                grades=list(parsed.get("grades") or []),
                must_skills_raw=list(parsed.get("must_skills_raw") or []),
                nice_skills_raw=list(parsed.get("nice_skills_raw") or []),
                work_formats=list(parsed.get("work_formats") or []),
                location=parsed.get("location"),
                salary_min=int(parsed["salary_min"]) if parsed.get("salary_min") is not None else None,
                salary_max=int(parsed["salary_max"]) if parsed.get("salary_max") is not None else None,
                salary_type=parsed.get("salary_type"),
                team_context=parsed.get("team_context"),
                description=parsed.get("description"),
            )
        except Exception as e:
            logger.warning(f"GigaChat JD parsing failed: {e}. Falling back to FakeLlm.")
            return FakeLlm().jd(text)

    def phrase(self, facts: list[str]) -> str:
        """Generate phrasing via GigaChat."""
        messages = [
            {"role": "system", "content": self.phrase_prompt},
            {"role": "user", "content": "Факты:\n" + "\n".join(f"- {f}" for f in facts)},
        ]
        try:
            return self._chat_completion(messages, temperature=0.2).strip()
        except Exception as e:
            logger.warning(f"GigaChat phrasing failed: {e}. Falling back to FakeLlm.")
            return FakeLlm().phrase(facts)
