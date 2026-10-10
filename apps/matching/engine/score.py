"""Match score over DTOs (ML.md §3). ML-0 stub: the old scoring.py rules on the final shapes."""
from __future__ import annotations

import datetime
from collections.abc import Sequence

from .types import COMPONENT_KEYS, GRADES, CandidateCtx, Component, NeedCtx, Reason, Scored, Weights

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
    if c.specialization != need.specialization or c.league_grade is None:
        return False
    if c.league_grade not in need.grades and not (
            need.allow_adjacent and any(_adjacent(c.league_grade, g) for g in need.grades)):
        return False
    if need.work_formats and c.work_formats and not set(need.work_formats) & set(c.work_formats):
        return False
    return True


def _score_one(need: NeedCtx, c: CandidateCtx, w: dict[str, float]) -> Scored:
    reasons: list[Reason] = []
    gaps: list[str] = []
    have = {e.skill_id: e for e in c.skills}
    must = list(need.must_skills)
    hits = [s for s in must if s in have]
    for s in must:
        if s in have:
            reasons.append(Reason("plus", f"Владеет {s}", have[s].source))
        else:
            reasons.append(Reason("minus", f"Нет обязательного навыка {s}", None))
            gaps.append(s)
    skill = len(hits) / len(must) if must else 0.7
    if not must:
        reasons.append(Reason("info", "В вакансии нет обязательных навыков", None))

    if c.league_grade in need.grades:
        grade = 1.0 if c.league_status == "confirmed" else 0.6
        reasons.append(Reason("plus" if grade == 1.0 else "info",
                              f"Грейд {c.league_grade} {'подтверждён тестом' if grade == 1.0 else 'не подтверждён'}",
                              "test" if grade == 1.0 else "declared"))
    else:
        grade = 0.2
        reasons.append(Reason("minus", "Грейд не совпадает с требованиями", None))

    rating = c.rating if c.rating is not None else 1000
    strength = min(1.0, max(0.0, (rating - 800) / 600))
    reasons.append(Reason("info", f"Рейтинг {rating}", "test" if c.rating is not None else None))

    salary = 1.0
    if c.salary_min:
        if c.salary_min > need.salary_max:
            salary = 0.2
            reasons.append(Reason("minus", "Ожидания выше бюджета вакансии", "declared"))
        else:
            reasons.append(Reason("plus", "Ожидания в пределах вилки", "declared"))
    else:
        salary = 0.5
        reasons.append(Reason("info", "Зарплатные ожидания не указаны", None))

    reasons.append(Reason("info", "Семантическое сходство пока не учитывается", None))
    reasons.append(Reason("info", "Активность пока не учитывается", None))
    values = {"skill": skill, "strength": strength, "grade": grade, "salary": salary,
              "semantic": 0.5, "freshness": 0.5}
    comps = tuple(Component(k, values[k], w[k], values[k] * w[k]) for k in COMPONENT_KEYS)
    return Scored(c.public_id, sum(x.contribution for x in comps), comps,
                  tuple(reasons), tuple(gaps))


def score_pool(need: NeedCtx, pool: Sequence[CandidateCtx], weights: Weights,
               now: datetime.datetime) -> list[Scored]:
    """Score every candidate; sorted by score desc, ties by public_id."""
    w = effective_weights(weights)
    scored = [_score_one(need, c, w) for c in pool]
    return sorted(scored, key=lambda s: (-s.score, s.public_id))
