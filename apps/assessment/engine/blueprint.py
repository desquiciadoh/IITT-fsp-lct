"""Screening blueprint for a job description (ML.md §3, ML-2, ML-12).

A JD's skills select the spec's topics whose skill lists they hit; each selected topic keeps
its category weight, boosted by the number of JD skills it covers:

    w'(topic) = w(topic) · (1 + hits(topic)),   normalised to Σ = 1 over the selected topics

With no hit (or no skills), the screening blueprint is the category blueprint. Weights are
rounded to 4 decimals and the largest absorbs the rounding, so Σ is exactly 1. Order: weight
descending, then topic id. A screening test never changes the grade (ARCHITECTURE §2.5).
"""
from __future__ import annotations

from ..families.base import SPECS
from .content import Content, load_content


def blueprint_for(spec: str, skill_ids: list[str], content: Content | None = None) -> list[tuple[str, float]]:
    """(topic, weight) pairs with Σ weight = 1."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    content = content or load_content()
    base = content.blueprints[spec]
    wanted = {str(s).strip().lower() for s in skill_ids if s and str(s).strip()}
    raw = {}
    for topic, w in base.items():
        hits = len(wanted & set(content.topics[topic].skills))
        if hits:
            raw[topic] = w * (1 + hits)
    if not raw:
        raw = dict(base)
    total = sum(raw.values())
    ranked = sorted(((t, round(v / total, 4)) for t, v in raw.items()), key=lambda tw: (-tw[1], tw[0]))
    drift = round(1.0 - sum(w for _, w in ranked), 4)
    top, w0 = ranked[0]
    ranked[0] = (top, round(w0 + drift, 4))
    return ranked
