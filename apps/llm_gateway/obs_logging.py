"""Structured, text-free logging for LLM Gateway operations (AI-R12).

Logs latency, provider, cache hit, source, and fallback reasons without leaking
raw text, PII, or model outputs into log streams.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("llm_gateway")


def log_llm_call(
    kind: str,
    provider: str,
    model: str,
    prompt_version: str,
    input_sha12: str,
    latency_ms: float,
    cache_hit: bool,
    source: str,
    fallback_reason: str | None = None,
) -> None:
    """Log one structured record per LLM or rules call."""
    payload: dict[str, Any] = {
        "event": "llm_call",
        "kind": kind,
        "provider": provider,
        "model": model,
        "prompt": prompt_version,
        "input_hash": input_sha12,
        "latency_ms": round(latency_ms, 1),
        "cache_hit": cache_hit,
        "source": source,
        "fallback_reason": fallback_reason,
    }
    logger.info("llm_call: kind=%s provider=%s source=%s latency=%.1fms hit=%s reason=%s",
                kind, provider, source, latency_ms, cache_hit, fallback_reason, extra=payload)
