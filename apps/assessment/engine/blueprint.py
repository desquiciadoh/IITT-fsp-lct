"""Screening blueprint for a job description (ML.md §3). ML-0 stub; ML-2 derives it from content."""
from __future__ import annotations

from ..families.base import SPECS


def blueprint_for(spec: str, skill_ids: list[str]) -> list[tuple[str, float]]:
    """(topic, weight) pairs with Σ weight = 1; [] means "no screening topics" (the stub, until ML-2)."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    return []
