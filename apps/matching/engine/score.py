"""Match score over DTOs (ML-4; ARCHITECTURE §2.6).

score = Σ_k value_k · weight_k, with weights rescaled to Σ = 100 (D4), so 0 <= score <= 100.
Candidates whose grade is not confirmed by a test are ranked ×0.75 (invariant 4), once: their
effective weights are multiplied by 0.75, so Σ contribution still equals the score
(invariant 7) and the chip says why. GradeFit does not penalise them again (D13). Every component emits at least one Russian reason chip; `gaps` lists the
must-have skills the candidate has no direct evidence for (display names).
score_pool scores every candidate it gets (BE applies the hard filters in SQL; the
reference is passes_hard_filters) and sorts by score desc, then public_id.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence

from .features import GRADE_RU, freshness_fit, grade_fit, salary_fit, semantic_fit, skill_fit
from .types import COMPONENT_KEYS, GRADES, CandidateCtx, Component, NeedCtx, Reason, Scored, Weights

UNCONFIRMED_FACTOR = 0.75
RANK_RU = {"cat3": "3 разряд", "cat2": "2 разряд", "cat1": "1 разряд", "kms": "КМС", "ms": "МС"}
TIER_RU = {"winner": "победитель", "prize_winner": "призёр", "finalist": "финалист", "participant": "участник"}

PRESETS: dict[str, Weights] = {
    "balanced": Weights(),
    "skills": Weights(skill=50, strength=20, grade=10, salary=5, semantic=10, freshness=5),
    "budget": Weights(skill=30, strength=15, grade=10, salary=35, semantic=5, freshness=5),
}


def effective_weights(weights: Weights) -> dict[str, float]:
    """Weights rescaled to sum to 100, so any slider setting keeps the score in 0..100."""
    raw = weights.as_dict()
    if any(v < 0 for v in raw.values()) or sum(raw.values()) <= 0:
        raise ValueError(f"weights must be >= 0 with a positive sum: {raw}")
    total = sum(raw.values())
    return {k: 100.0 * v / total for k, v in raw.items()}


def preset(name: str) -> Weights:
    if name not in PRESETS:
        raise ValueError(f"unknown preset: {name!r}")
    return PRESETS[name]


def _adjacent(a: str, b: str) -> bool:
    return abs(GRADES.index(a) - GRADES.index(b)) == 1


def passes_hard_filters(need: NeedCtx, c: CandidateCtx) -> bool:
    """Reference for BE's SQL prefilter: specialization, grade (+adjacent if allowed), work format."""
    if c.specialization != need.specialization or c.league_grade is None:
        return False
    if c.league_grade not in need.grades and not (
            need.allow_adjacent and any(_adjacent(c.league_grade, g) for g in need.grades)):
        return False
    if need.work_formats and c.work_formats and not set(need.work_formats) & set(c.work_formats):
        return False
    return True


def _strength_component(c: CandidateCtx) -> tuple[float, list[Reason]]:
    reasons: list[Reason] = []
    if c.strength is None:
        reasons.append(Reason("info", "Сила профиля ещё не рассчитана", None))
        value = 0.0
    else:
        value = min(1.0, max(0.0, c.strength / 100.0))
        text = f"Сила профиля {round(c.strength)}"
        if c.percentile is not None:
            text += f" (топ {max(1, round(100 - c.percentile))}% лиги)"
        reasons.append(Reason("plus" if value >= 0.6 else "info", text, "test"))
    if c.fsp_results or c.fsp_rank:
        parts = []
        if c.fsp_rank:
            parts.append(RANK_RU.get(c.fsp_rank, c.fsp_rank))
        tiers = [r.tier for r in set(c.fsp_results)]
        for tier in ("winner", "prize_winner", "finalist", "participant"):
            n = tiers.count(tier)
            if n:
                parts.append(f"{TIER_RU[tier]} ×{n}")
        reasons.append(Reason("plus", "Достижения ФСП: " + ", ".join(parts), "fsp"))
    else:
        reasons.append(Reason("info", "Без истории ФСП: сила по квалификации платформы", None))
    return value, reasons


def score_candidate(need: NeedCtx, c: CandidateCtx, weights: Weights, now: datetime.datetime) -> Scored:
    w = effective_weights(weights)
    reasons: list[Reason] = []
    skill, r_skill, gaps = skill_fit(need, c)
    strength, r_strength = _strength_component(c)
    grade, r_grade = grade_fit(need, c)
    salary, r_salary = salary_fit(need, c)
    semantic, r_semantic = semantic_fit(need, c)
    fresh, r_fresh = freshness_fit(c, now)
    values = {"skill": skill, "strength": strength, "grade": grade, "salary": salary,
              "semantic": semantic, "freshness": fresh}
    for r in (r_skill, r_strength, r_grade, r_salary, r_semantic, r_fresh):
        reasons += r
    factor = 1.0
    if c.league_status != "confirmed":
        factor = UNCONFIRMED_FACTOR
        grade_name = GRADE_RU.get(c.league_grade or "", "")
        reasons.append(Reason("minus", f"Грейд {grade_name} не подтверждён: ранжирование ×0.75".replace("  ", " "),
                              None))
    comps = tuple(Component(k, values[k], w[k] * factor, values[k] * w[k] * factor) for k in COMPONENT_KEYS)
    return Scored(public_id=c.public_id, score=sum(x.contribution for x in comps), components=comps,
                  reasons=tuple(reasons), gaps=tuple(gaps))


def score_pool(need: NeedCtx, pool: Sequence[CandidateCtx], weights: Weights,
               now: datetime.datetime) -> list[Scored]:
    """Score every candidate; sorted by score desc, ties by public_id."""
    effective_weights(weights)                   # fail fast on bad weights, even for an empty pool
    scored = [score_candidate(need, c, weights, now) for c in pool]
    return sorted(scored, key=lambda s: (-s.score, s.public_id))
