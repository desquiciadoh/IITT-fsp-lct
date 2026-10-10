"""Grade policy (ML-3): decision, promotion, fallback, rating. Cuts come from content/grades.yaml.

    confirmed          θ̂ ≥ cut(claimed), and the test ran to a stop rule (an abandoned or
                       unfinished session never confirms, decision D8)
    promotion_unlocked confirmed and P(θ ≥ cut(next grade) | data) ≥ 0.9
    fallback_grade     complete but unconfirmed: the highest lower grade g with P(θ ≥ cut(g) | data) ≥ 0.8
    result_grade       the band θ̂ falls into (three separating cuts)
    rating             round(1000 + 200·θ̂) ± round(1.96·200·SE)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..families.base import GRADES
from .content import Content, load_content
from .irt import moments, prob_at_least

PROMOTION_P = 0.9
FALLBACK_P = 0.8


@dataclass(frozen=True)
class Decision:
    theta: float
    se: float
    rating: int
    rating_ci: int
    result_grade: str
    decision: str
    promotion_unlocked: bool
    fallback_grade: str | None


def band_of(theta: float, content: Content | None = None) -> str:
    cuts = (content or load_content()).band_cuts
    return GRADES[sum(theta >= x for x in cuts)]


def decide(post: np.ndarray, claimed: str, complete: bool, content: Content | None = None) -> Decision:
    content = content or load_content()
    theta, se = moments(post)
    idx = GRADES.index(claimed)
    confirmed = complete and theta >= content.grade(claimed).theta_cut
    promotion = bool(confirmed and idx + 1 < len(GRADES)
                     and prob_at_least(post, content.grade(GRADES[idx + 1]).theta_cut) >= PROMOTION_P)
    fallback = None
    if complete and not confirmed:          # an abandoned session offers no fallback (BE H6)
        for g in reversed(GRADES[:idx]):
            if prob_at_least(post, content.grade(g).theta_cut) >= FALLBACK_P:
                fallback = g
                break
    return Decision(
        theta=theta, se=se,
        rating=round(content.rating_base + content.rating_per_theta * theta),
        rating_ci=round(1.96 * content.rating_per_theta * se),
        result_grade=band_of(theta, content),
        decision="confirmed" if confirmed else "unconfirmed",
        promotion_unlocked=promotion, fallback_grade=fallback)
