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

import logging
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
_NO_KEY_LOGGED = False


def get_gateway(config: GatewayConfig | None = None) -> LlmGateway:
    """Build or retrieve the process-wide cached LlmGateway instance.

    Per AI-R8 and AI-R14:
    - Does not mutate environment via load_dotenv().
    - Caches instances by GatewayConfig (frozen dataclass).
    - Logs error once and returns FakeLlm if gigachat requested without GIGACHAT_AUTH_KEY.
    """
    global _NO_KEY_LOGGED

    if config is None:
        provider = os.getenv("LLM_PROVIDER", "fake")
        auth_key = os.getenv("GIGACHAT_AUTH_KEY")
        scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        ca_bundle = os.getenv("GIGACHAT_CA_BUNDLE")
        try:
            timeout_s = float(os.getenv("LLM_TIMEOUT_S", "10.0"))
        except ValueError:
            timeout_s = 10.0

        try:
            from django.conf import settings
            from django.core.exceptions import ImproperlyConfigured

            try:
                provider = getattr(settings, "LLM_PROVIDER", provider)
                auth_key = getattr(settings, "GIGACHAT_AUTH_KEY", auth_key)
                scope = getattr(settings, "GIGACHAT_SCOPE", scope)
                model = getattr(settings, "GIGACHAT_MODEL", model)
                ca_bundle = getattr(settings, "GIGACHAT_CA_BUNDLE", ca_bundle)
                timeout_s = float(getattr(settings, "LLM_TIMEOUT_S", timeout_s))
            except ImproperlyConfigured:
                pass  # used outside Django (scripts, pure tests): env vars only
        except ImportError:
            pass

        config = GatewayConfig(
            provider=provider,
            auth_key=auth_key,
            scope=scope,
            model=model,
            ca_bundle=ca_bundle,
            timeout_s=timeout_s,
        )

    if config.provider == "gigachat":
        if not config.auth_key:
            if not _NO_KEY_LOGGED:
                logger.error("GigaChat provider requested but GIGACHAT_AUTH_KEY is missing. Using FakeLlm.")
                _NO_KEY_LOGGED = True
            return FakeLlm(fallback_reason="no_key")

        with _GATEWAY_LOCK:
            if config not in _GATEWAY_INSTANCES:
                from .gigachat import GigaChatLlm
                _GATEWAY_INSTANCES[config] = GigaChatLlm(config)
            return _GATEWAY_INSTANCES[config]

    return FakeLlm()


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
