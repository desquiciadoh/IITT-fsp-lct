"""Protocols and configuration for the LLM Gateway.

Pure Python protocols and config without ORM or view dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .types import JdDraft, ResumeDraft


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
