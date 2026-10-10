"""Cache and fallback steps shared by parse_resume and parse_jd (AI.md §3, steps 2-5).

This is the only place where the rules fallback happens: a gateway raises, the pipeline answers
with FakeLlm and says why (`fallback_reason`). Only a validated LLM answer is cached, and a
cached answer is used only if it survives validation unchanged.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .base import Cache, LlmError, LlmGateway, LlmSchemaError
from .types import Source

logger = logging.getLogger(__name__)

CACHE_TTL_S = 7 * 86400
CACHE_VERSION = 1

DraftT = TypeVar("DraftT")


@dataclass(frozen=True)
class Outcome(Generic[DraftT]):
    draft: DraftT
    source: Source
    fallback_reason: str | None
    cache_hit: bool
    model: str
    input_sha12: str


def cache_key(kind: str, prompt_version: str, model: str, text: str) -> str:
    raw = f"{kind}|{prompt_version}|{model}|{text}".encode("utf-8")
    return f"llm:cache:{hashlib.sha256(raw).hexdigest()}"


def model_name(gateway: LlmGateway) -> str:
    return getattr(getattr(gateway, "config", None), "model", None) or gateway.name


def run(
    *,
    kind: str,
    prompt_version: str,
    redacted_text: str,
    is_clean: bool,
    gateway: LlmGateway,
    cache: Cache | None,
    call_llm: Callable[[], Any],
    call_rules: Callable[[], Any],
    validate: Callable[..., DraftT],
) -> Outcome[DraftT]:
    """Steps 2-5: PII gate, cache, gateway call, fallback, validation."""
    model = model_name(gateway)
    sha12 = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()[:12]

    def rules(reason: str) -> Outcome[DraftT]:
        draft = validate(dataclasses.asdict(call_rules()), require_data=False)
        return Outcome(draft, "rules", reason, False, model, sha12)

    if not is_clean:
        return rules("pii_residual")
    if gateway.name == "fake":
        # FakeLlm says why it is the gateway: "provider_fake", or "no_key" from get_gateway()
        return rules(getattr(gateway, "fallback_reason", "provider_fake"))

    key = cache_key(kind, prompt_version, model, redacted_text)
    cached = _cache_get(cache, key, validate)
    if cached is not None:
        return Outcome(cached, "llm", None, True, model, sha12)

    try:
        answer = call_llm()
        payload = dataclasses.asdict(answer) if dataclasses.is_dataclass(answer) else answer
        draft = validate(payload)
    except LlmError as e:
        logger.warning("llm %s failed: %s (%s)", kind, type(e).__name__, e.reason)
        return rules(e.reason)
    except TimeoutError as e:
        logger.warning("llm %s failed: %s (timeout)", kind, type(e).__name__)
        return rules("timeout")
    except Exception as e:  # a bug in an adapter must not break the upload: rules, and say so
        logger.error("llm %s crashed: %s", kind, type(e).__name__)
        return rules("error")

    _cache_set(cache, key, {
        "v": CACHE_VERSION,
        "source": "llm",
        "prompt": prompt_version,
        "model": model,
        "draft": dataclasses.asdict(draft),
    })
    return Outcome(draft, "llm", None, False, model, sha12)


def _cache_get(cache: Cache | None, key: str, validate: Callable[..., DraftT]) -> DraftT | None:
    if cache is None:
        return None
    try:
        entry = cache.get(key)
    except Exception as e:
        logger.warning("llm cache get failed: %s", type(e).__name__)
        return None
    if not entry:
        return None
    try:
        obj = json.loads(entry) if isinstance(entry, (str, bytes)) else entry
        if not isinstance(obj, dict) or obj.get("v") != CACHE_VERSION or obj.get("source") != "llm":
            return None
        stored = obj["draft"]
        draft = validate(stored)
    except (ValueError, TypeError, KeyError, ArithmeticError, LlmSchemaError):
        return None
    # Only validated answers are stored, so a valid entry is a fixed point of validation.
    if dataclasses.asdict(draft) != stored:
        return None
    return draft


def _cache_set(cache: Cache | None, key: str, entry: dict[str, Any]) -> None:
    if cache is None:
        return
    try:
        # ttl is positional: Django's cache.set(key, value, timeout) accepts it too
        cache.set(key, json.dumps(entry, ensure_ascii=False), CACHE_TTL_S)
    except Exception as e:
        logger.warning("llm cache set failed: %s", type(e).__name__)
