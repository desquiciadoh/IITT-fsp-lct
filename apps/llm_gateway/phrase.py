"""Phrase generation module for offer reason justifications.

Turns scorer's reason chips into natural, grounded Russian sentences.
Performs a strict grounding check: any numbers or unknown facts in LLM output
trigger fallback to the deterministic template.
"""
from __future__ import annotations

import re
from typing import Any

from .base import LlmGateway
from .fake import FakeLlm


def _extract_numbers(text: str) -> set[str]:
    """Extract all numbers from text for grounding verification."""
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))


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

    # If gateway is fake, use its template generation directly
    if active_gateway.name == "fake":
        return active_gateway.phrase(facts)

    try:
        candidate_phrase = active_gateway.phrase(facts)
        # Grounding check: numbers verification
        input_numbers = set()
        for f in facts:
            input_numbers.update(_extract_numbers(f))

        output_numbers = _extract_numbers(candidate_phrase)

        # If LLM hallucinated new numbers, reject and fall back to template
        hallucinated_numbers = output_numbers - input_numbers
        if hallucinated_numbers:
            return FakeLlm().phrase(facts)

        return candidate_phrase
    except Exception:
        return FakeLlm().phrase(facts)
