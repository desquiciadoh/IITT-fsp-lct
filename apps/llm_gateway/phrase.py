"""Phrase generation for offer reason justifications (AI-7, AI-R9).

Turns the scorer's reason chips into one or two grounded Russian sentences:
- every number in the output must be in the facts (250 000 == 250000, 4,5 == 4.5)
- every taxonomy skill in the output must be in the facts
- at most 300 characters and 2 sentences, no PII placeholders
Any violation or provider failure gives the deterministic template.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time

from taxonomy import extract_skills

from .base import PHRASE_PROMPT, LlmGateway
from .fake import FakeLlm
from .obs_logging import log_llm_call

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


def phrase(facts: list[str], *, gateway: LlmGateway | None = None) -> str:
    """One or two Russian sentences grounded strictly in `facts`; the template on any doubt."""
    if not facts:
        return "Кандидат соответствует ключевым требованиям позиции."

    t0 = time.monotonic()
    from . import get_gateway
    active_gateway = gateway or get_gateway()
    input_sha12 = hashlib.sha256("\n".join(facts).encode("utf-8")).hexdigest()[:12]
    source, fallback_reason = "rules", getattr(active_gateway, "fallback_reason", None)
    result: str

    if active_gateway.name == "fake":
        result = FakeLlm().phrase(facts)
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
            else:
                fallback_reason = f"grounding_{rejection}"
                logger.warning("phrase rejected: %s", rejection)
                result = FakeLlm().phrase(facts)

    log_llm_call(
        kind="phrase",
        provider=active_gateway.name,
        model=getattr(getattr(active_gateway, "config", None), "model", None) or active_gateway.name,
        prompt_version=PHRASE_PROMPT,
        input_sha12=input_sha12,
        latency_ms=(time.monotonic() - t0) * 1000,
        cache_hit=False,
        source=source,
        fallback_reason=fallback_reason,
    )
    return result
