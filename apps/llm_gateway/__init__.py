"""LLM Gateway application package.

Exposes primary entry points:
- parse_resume
- parse_jd
- phrase
- redact
- extract_text
- get_gateway
- UnreadablePdf, LlmError, LlmUnavailable, LlmSchemaError
"""
from __future__ import annotations

import dataclasses
import logging
import math
import os
import threading

from .base import Cache, GatewayConfig, LlmError, LlmGateway, LlmSchemaError, LlmUnavailable
from .fake import FakeLlm
from .jd import parse_jd
from .pdf_text import extract_text
from .phrase import phrase
from .redact import redact
from .resume import parse_resume
from .types import (
    JdDraft,
    JdParseResult,
    Redacted,
    ResumeDraft,
    ResumeParseResult,
    Source,
    UnreadablePdf,
)

logger = logging.getLogger(__name__)

_GATEWAY_INSTANCES: dict[GatewayConfig, LlmGateway] = {}
_GATEWAY_LOCK = threading.Lock()
_LOGGED_ONCE: set[str] = set()
_DEFAULT_TIMEOUT_S = 10.0


def _error_once(key: str, message: str, *args: object) -> None:
    if key not in _LOGGED_ONCE:
        _LOGGED_ONCE.add(key)
        logger.error(message, *args)


def _timeout_s(value: object) -> float:
    """LLM_TIMEOUT_S as a positive number of seconds; a bad value is logged, not silently kept."""
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        seconds = math.nan
    if not math.isfinite(seconds) or seconds <= 0:
        _error_once(f"timeout:{value!r}", "LLM_TIMEOUT_S=%r is not a positive number, using %s", value, _DEFAULT_TIMEOUT_S)
        return _DEFAULT_TIMEOUT_S
    return seconds


def get_gateway(config: GatewayConfig | None = None) -> LlmGateway:
    """Build or retrieve the process-wide cached LlmGateway instance.

    Per AI-R8 and AI-R14:
    - Does not mutate environment via load_dotenv().
    - Caches instances by GatewayConfig (frozen dataclass).
    - Logs error once and returns FakeLlm if gigachat requested without GIGACHAT_AUTH_KEY,
      or if LLM_PROVIDER is neither "fake" nor "gigachat".
    """
    if config is None:
        provider = os.getenv("LLM_PROVIDER", "fake")
        auth_key = os.getenv("GIGACHAT_AUTH_KEY")
        scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        ca_bundle = os.getenv("GIGACHAT_CA_BUNDLE")
        timeout: object = os.getenv("LLM_TIMEOUT_S", _DEFAULT_TIMEOUT_S)

        try:
            from django.conf import settings
            from django.core.exceptions import ImproperlyConfigured

            try:
                provider = getattr(settings, "LLM_PROVIDER", provider)
                auth_key = getattr(settings, "GIGACHAT_AUTH_KEY", auth_key)
                scope = getattr(settings, "GIGACHAT_SCOPE", scope)
                model = getattr(settings, "GIGACHAT_MODEL", model)
                ca_bundle = getattr(settings, "GIGACHAT_CA_BUNDLE", ca_bundle)
                timeout = getattr(settings, "LLM_TIMEOUT_S", timeout)
            except ImproperlyConfigured:
                pass  # used outside Django (scripts, pure tests): env vars only
        except ImportError:
            pass

        config = GatewayConfig(
            provider=provider,
            auth_key=auth_key,
            scope=scope,
            model=model,
            ca_bundle=ca_bundle or None,
            timeout_s=timeout,  # type: ignore[arg-type]  # validated just below
        )

    config = dataclasses.replace(
        config,
        provider=str(config.provider or "fake").strip().lower(),
        timeout_s=_timeout_s(config.timeout_s),
    )

    if config.provider == "fake":
        return FakeLlm()
    if config.provider != "gigachat":
        _error_once(f"provider:{config.provider}", "Unknown LLM_PROVIDER=%r, using the rules", config.provider)
        return FakeLlm(fallback_reason="provider_unknown")
    if not config.auth_key:
        _error_once("no_key", "GigaChat provider requested but GIGACHAT_AUTH_KEY is missing. Using FakeLlm.")
        return FakeLlm(fallback_reason="no_key")

    with _GATEWAY_LOCK:
        if config not in _GATEWAY_INSTANCES:
            from .gigachat import GigaChatLlm
            _GATEWAY_INSTANCES[config] = GigaChatLlm(config)
        return _GATEWAY_INSTANCES[config]


__all__ = [
    "Cache",
    "FakeLlm",
    "GatewayConfig",
    "JdDraft",
    "JdParseResult",
    "LlmError",
    "LlmGateway",
    "LlmSchemaError",
    "LlmUnavailable",
    "Redacted",
    "ResumeDraft",
    "ResumeParseResult",
    "Source",
    "UnreadablePdf",
    "extract_text",
    "get_gateway",
    "parse_jd",
    "parse_resume",
    "phrase",
    "redact",
]
