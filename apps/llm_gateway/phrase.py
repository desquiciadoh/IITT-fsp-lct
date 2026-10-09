"""Phrase generation module for offer reason justifications.

Turns scorer's reason chips into natural, grounded Russian sentences.
Performs strict grounding checks adhering to AI.md AI-R9:
- Normalized numbers verification (supports 250 000 == 250000, commas/dots)
- Skill grounding against taxonomy (extract_skills on facts vs output)
- Rejects outputs > 300 chars or > 2 sentences or containing PII placeholders
- Fallback to deterministic template on any violation or provider failure
"""
from __future__ import annotations

import logging
import re

from taxonomy import extract_skills

from .base import LlmGateway
from .fake import FakeLlm

logger = logging.getLogger(__name__)


def _extract_normalized_numbers(text: str) -> set[float]:
    """Extract and normalize numbers from text (merges separated digit groups e.g. 250 000)."""
    collapsed = re.sub(r"(?<=\d)[\s\xa0]+(?=\d)", "", text)
    numbers: set[float] = set()
    for token in re.findall(r"\b\d+(?:[.,]\d+)?\b", collapsed):
        try:
            numbers.add(float(token.replace(",", ".")))
        except ValueError:
            pass
    return numbers


def _count_sentences(text: str) -> int:
    """Count sentences by splitting on punctuation terminators."""
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    return len(sentences)


def phrase(facts: list[str], *, gateway: LlmGateway | None = None) -> str:
    """Phrase list of factual reasons into a grounded summary sentence.

    Args:
        facts: Factual statements from the matching scorer.
        gateway: Optional LlmGateway. If None or fake, uses template generation.

    Returns:
        One or two natural Russian sentences grounded strictly in input facts.
    """
    if not facts:
        return "Кандидат соответствует ключевым требованиям позиции."

    from . import get_gateway
    active_gateway = gateway or get_gateway()

    # If gateway is fake, use template generation directly
    if active_gateway.name == "fake":
        return active_gateway.phrase(facts)

    try:
        candidate_phrase = active_gateway.phrase(facts).strip()

        # 1. Length constraint: <= 300 chars
        if len(candidate_phrase) > 300:
            logger.warning(f"Phrase rejected: length {len(candidate_phrase)} > 300")
            return FakeLlm().phrase(facts)

        # 2. Sentences count: <= 2 sentences
        if _count_sentences(candidate_phrase) > 2:
            logger.warning("Phrase rejected: more than 2 sentences")
            return FakeLlm().phrase(facts)

        # 3. No PII placeholders allowed
        if re.search(r"\[(NAME|PHONE|EMAIL|TG|URL)\]", candidate_phrase):
            logger.warning("Phrase rejected: contains PII placeholder")
            return FakeLlm().phrase(facts)

        # 4. Number grounding: all numbers in candidate must exist in facts
        input_numbers: set[float] = set()
        for f in facts:
            input_numbers.update(_extract_normalized_numbers(f))
        output_numbers = _extract_normalized_numbers(candidate_phrase)

        hallucinated_numbers = output_numbers - input_numbers
        if hallucinated_numbers:
            logger.warning(f"Phrase rejected: hallucinated numbers {hallucinated_numbers}")
            return FakeLlm().phrase(facts)

        # 5. Skill grounding: all taxonomy skills mentioned in candidate must exist in facts
        input_skills: set[str] = set()
        for f in facts:
            matches, _ = extract_skills(f)
            input_skills.update(m.skill_id for m in matches)

        output_matches, _ = extract_skills(candidate_phrase)
        output_skills = {m.skill_id for m in output_matches}

        hallucinated_skills = output_skills - input_skills
        if hallucinated_skills:
            logger.warning(f"Phrase rejected: hallucinated skills {hallucinated_skills}")
            return FakeLlm().phrase(facts)

        return candidate_phrase

    except Exception as e:
        logger.warning(f"Gateway phrasing failed ({type(e).__name__}), falling back to template")
        return FakeLlm().phrase(facts)
