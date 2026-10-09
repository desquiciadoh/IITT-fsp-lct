"""LLM Gateway application package.

Exposes primary entry points:
- parse_resume
- parse_jd
- phrase
- redact
- extract_text
- get_gateway
- UnreadablePdf
"""
from __future__ import annotations

import os
from typing import Any

from .base import Cache, GatewayConfig, LlmGateway
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


def get_gateway(config: GatewayConfig | None = None) -> LlmGateway:
    """Build or retrieve the configured LlmGateway instance.

    If config is not provided, attempts to read from django.conf.settings
    or environment variables. Falls back to FakeLlm.
    """
    if config is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

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
            provider = getattr(settings, "LLM_PROVIDER", provider)
            auth_key = getattr(settings, "GIGACHAT_AUTH_KEY", auth_key)
            scope = getattr(settings, "GIGACHAT_SCOPE", scope)
            model = getattr(settings, "GIGACHAT_MODEL", model)
            ca_bundle = getattr(settings, "GIGACHAT_CA_BUNDLE", ca_bundle)
            timeout_s = getattr(settings, "LLM_TIMEOUT_S", timeout_s)
        except Exception:
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
        try:
            from .gigachat import GigaChatLlm
            return GigaChatLlm(config)
        except Exception:
            return FakeLlm()

    return FakeLlm()


__all__ = [
    "Cache",
    "GatewayConfig",
    "JdDraft",
    "JdParseResult",
    "LlmGateway",
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
