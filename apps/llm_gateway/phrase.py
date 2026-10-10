"""Phrase generation for offer reason justifications (AI-7, AI-R9).

Turns the scorer's reason chips into one or two grounded Russian sentences:
- every number in the output must be in the facts (250 000 == 250000, 4,5 == 4.5)
- every taxonomy skill in the output must be in the facts
- at most 300 characters and 2 sentences, no PII placeholders
Any violation or provider failure gives the deterministic template. Facts with personal data
are never sent; accepted sentences are cached by sha256(kind, prompt version, model, facts).
"""
from __future__ import annotations

import hashlib
import logging
import re
import time

from taxonomy import extract_skills

from . import pipeline
from .base import PHRASE_PROMPT, Cache, LlmGateway
from .fake import FakeLlm
from .obs_logging import log_llm_call
from .redact import assert_clean, redact

logger = logging.getLogger(__name__)

MAX_CHARS = 300
MAX_SENTENCES = 2
# A sentence ends at . ! ? or … followed by a space or the end: "4.5 года" and "Node.js" do not
_SENTENCE_END_RE = re.compile(r"[.!?…]+(?=\s|$)")
_PLACEHOLDER_RE = re.compile(r"\[(?:NAME|PHONE|EMAIL|TG|URL)\]")


def _extract_normalized_numbers(text: str) -> set[float]:
    """Numbers with digit groups merged: "250 000" -> 250000.0, "4,5" -> 4.5."""
    collapsed = re.sub(r"(?<=\d)[\s\xa0]+(?=\d)", "", text)
    return {float(token.replace(",", ".")) for token in re.findall(r"\d+(?:[.,]\d+)?", collapsed)}


def _count_sentences(text: str) -> int:
    return len([part for part in _SENTENCE_END_RE.split(text) if part.strip()])


def _rejection(candidate: str, facts: list[str]) -> str | None:
    """Why the model's sentence cannot be shown, or None if it is grounded."""
    if len(candidate) > MAX_CHARS:
        return "length"
    if _count_sentences(candidate) > MAX_SENTENCES:
        return "sentences"
    if _PLACEHOLDER_RE.search(candidate):
        return "placeholder"
    fact_text = "\n".join(facts)
    if _extract_normalized_numbers(candidate) - _extract_normalized_numbers(fact_text):
        return "numbers"
    fact_skills = {m.skill_id for m in extract_skills(fact_text)[0]}
    if {m.skill_id for m in extract_skills(candidate)[0]} - fact_skills:
        return "skills"
    return None


def phrase(facts: list[str], *, gateway: LlmGateway | None = None, cache: Cache | None = None) -> str:
    """One or two Russian sentences grounded strictly in `facts`; the template on any doubt.

    No facts give "" (nothing to claim). Facts that contain personal data never reach the
    provider ("pii_residual"). Accepted LLM sentences are cached by prompt, model and facts.
    """
    facts = [f.strip() for f in facts if f and f.strip()]
    if not facts:
        return ""

    t0 = time.monotonic()
    from . import get_gateway
    active_gateway = gateway or get_gateway()
    joined = "\n".join(facts)
    input_sha12 = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    model = pipeline.model_name(active_gateway)
    source, fallback_reason = "rules", getattr(active_gateway, "fallback_reason", None)
    cache_hit = False
    result: str

    redacted = redact(joined, header_names=False)
    has_pii = any(redacted.found.values()) or not assert_clean(redacted)[0]
    key = pipeline.cache_key("phrase", PHRASE_PROMPT, model, joined)

    if active_gateway.name == "fake":
        result = FakeLlm().phrase(facts)
    elif has_pii:
        fallback_reason = "pii_residual"
        result = FakeLlm().phrase(facts)
    elif (cached := _cache_get(cache, key, facts)) is not None:
        source, fallback_reason, result, cache_hit = "llm", None, cached, True
    else:
        try:
            candidate = active_gateway.phrase(facts).strip()
            rejection = _rejection(candidate, facts)
        except Exception as e:  # provider failure: the template, and say why
            fallback_reason = getattr(e, "reason", None) or ("timeout" if isinstance(e, TimeoutError) else "error")
            logger.warning("phrase failed: %s (%s)", type(e).__name__, fallback_reason)
            result = FakeLlm().phrase(facts)
        else:
            if rejection is None:
                source, fallback_reason, result = "llm", None, candidate
                _cache_set(cache, key, candidate)
            else:
                fallback_reason = f"grounding_{rejection}"
                logger.warning("phrase rejected: %s", rejection)
                result = FakeLlm().phrase(facts)

    log_llm_call(
        kind="phrase",
        provider=active_gateway.name,
        model=model,
        prompt_version=PHRASE_PROMPT,
        input_sha12=input_sha12,
        latency_ms=(time.monotonic() - t0) * 1000,
        cache_hit=cache_hit,
        source=source,
        fallback_reason=fallback_reason,
    )
    return result


def _cache_get(cache: Cache | None, key: str, facts: list[str]) -> str | None:
    """A cached sentence, re-checked against the facts; None on a miss or any doubt."""
    if cache is None:
        return None
    try:
        entry = cache.get(key)
    except Exception as e:
        logger.warning("phrase cache get failed: %s", type(e).__name__)
        return None
    if not isinstance(entry, str) or not entry or _rejection(entry, facts) is not None:
        return None
    return entry


def _cache_set(cache: Cache | None, key: str, sentence: str) -> None:
    if cache is None:
        return
    try:
        cache.set(key, sentence, pipeline.CACHE_TTL_S)  # ttl positional, as Django's cache expects
    except Exception as e:
        logger.warning("phrase cache set failed: %s", type(e).__name__)
