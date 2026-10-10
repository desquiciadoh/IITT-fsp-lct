"""Protocols and configuration for the LLM Gateway.

Pure Python protocols and config without ORM or view dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .types import JdDraft, ResumeDraft

# One constant per prompt: GigaChatLlm loads prompts/<version>.md and the orchestrators put the
# same string into the cache key, so a new prompt file invalidates the cache (AI-R2).
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
RESUME_PROMPT = "resume.v2"
JD_PROMPT = "jd.v1"
PHRASE_PROMPT = "phrase.v1"


def load_prompt(version: str) -> str:
    """Read prompts/<version>.md. A missing prompt is a deployment error, never a silent fallback."""
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


class LlmError(Exception):
    """Base error for LLM provider failures."""
    def __init__(self, message: str, reason: str = "http_error") -> None:
        super().__init__(message)
        self.reason = reason


class LlmUnavailable(LlmError):
    """Raised on auth failure, network timeout, 5xx, 429, or missing key."""


class LlmSchemaError(LlmError):
    """Raised when output is invalid JSON or fails schema validation."""


@runtime_checkable
class LlmGateway(Protocol):
    """Protocol for LLM Gateways (FakeLlm, GigaChatLlm)."""

    name: str  # "fake" | "gigachat"

    def resume(self, redacted_text: str) -> ResumeDraft:
        """Extract structured resume draft from redacted CV text."""
        ...

    def jd(self, text: str) -> JdDraft:
        """Extract structured job description draft from vacancy text."""
        ...

    def phrase(self, facts: list[str]) -> str:
        """Phrase scorer's factual reason chips into natural text (P1)."""
        ...


@runtime_checkable
class Cache(Protocol):
    """Cache protocol compatible with Django's cache or a dict/dummy cache."""

    def get(self, key: str) -> Any:
        ...

    def set(self, key: str, value: Any, ttl: int) -> None:
        ...


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration for LLM Gateway instances."""

    provider: str = "fake"  # "fake" | "gigachat"
    auth_key: str | None = None
    scope: str = "GIGACHAT_API_PERS"
    model: str = "GigaChat-2"
    ca_bundle: str | None = None
    timeout_s: float = 10.0
