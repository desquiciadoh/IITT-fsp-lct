"""Counterfactual relaxations and acceptance likelihood (ML-10, AI-12). Pure: no Django, no ORM.

Relaxations. A candidate *qualifies* for a need when they pass the hard filters (`score.
passes_hard_filters`), have direct evidence for every must-have (no `gaps`, the same rule the
score's gap chips use) and their salary expectation is affordable at all (SalaryFit > 0, i.e. at
most 125 % of the budget, the point where the score's salary component reaches 0). Each
counterfactual (drop one must-have, allow adjacent grades, add a work format, raise the budget by
20 %) is re-counted with the same rule, and the top 3 by added candidates are returned (ties by
text). One rule for the score, the chips and the counterfactuals: an employer who applies a
suggestion sees exactly the promised candidates appear.

Acceptance likelihood is a transparent heuristic, not a fitted model (there is no offer outcome
data yet): a weighted score of salary fit (0.40), format fit (0.25), recency of activity (0.20) and
league status (0.15), mapped to low < 0.45 ≤ medium < 0.78 ≤ high. A format conflict caps the
result at medium, and an offer more than 25 % below the candidate's minimum is low. Recency is
measured against the caller's `now`, so the result is reproducible.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .features import salary_fit, skill_fit, skill_name
from .salary import to_gross
from .score import passes_hard_filters
from .types import CandidateCtx, NeedCtx

FORMAT_RU: dict[str, str] = {"remote": "удалённый формат", "hybrid": "гибридный формат", "office": "офисный формат"}
BUDGET_STEP = 0.20
TOP = 3


@dataclass(frozen=True)
class Relaxation:
    change: str     # "убрать Kubernetes из обязательных"
    delta: int      # +23 candidates


def qualifies(need: NeedCtx, c: CandidateCtx) -> bool:
    if not passes_hard_filters(need, c):
        return False
    _, _, gaps = skill_fit(need, c)
    salary, _ = salary_fit(need, c)
    return not gaps and salary > 0


def _count(need: NeedCtx, pool: Sequence[CandidateCtx]) -> int:
    return sum(1 for c in pool if qualifies(need, c))


def relaxations(need: NeedCtx, pool: Sequence[CandidateCtx]) -> list[Relaxation]:
    """Top 3 counterfactual relaxations by the number of candidates they add (delta > 0 only)."""
    if not pool:
        return []
    base = _count(need, pool)
    options: list[tuple[str, NeedCtx]] = []
    for s in need.must_skills:
        options.append((f"убрать {skill_name(s)} из обязательных",
                        dataclasses.replace(need, must_skills=tuple(x for x in need.must_skills if x != s))))
    if not need.allow_adjacent:
        options.append(("разрешить смежные грейды", dataclasses.replace(need, allow_adjacent=True)))
    if need.work_formats:
        for fmt in ("remote", "hybrid", "office"):
            if fmt not in need.work_formats:
                options.append((f"добавить {FORMAT_RU[fmt]}",
                                dataclasses.replace(need, work_formats=(*need.work_formats, fmt))))
    options.append((f"увеличить бюджет на {round(BUDGET_STEP * 100)} %",
                    dataclasses.replace(need, salary_max=round(need.salary_max * (1 + BUDGET_STEP)))))
    found = [Relaxation(text, _count(relaxed, pool) - base) for text, relaxed in options]
    found = [r for r in found if r.delta > 0]
    found.sort(key=lambda r: (-r.delta, r.change))
    return found[:TOP]


def _salary_score(offer_gross: float, c: CandidateCtx) -> float:
    kind = c.salary_type or "gross"
    lo = to_gross(c.salary_min, kind) if c.salary_min else None
    hi = to_gross(c.salary_max, kind) if c.salary_max else None
    if lo is not None and hi is not None and hi > lo:
        if offer_gross >= hi * 1.05:
            return 1.0
        if offer_gross >= hi:
            return 0.90
        if offer_gross >= lo:
            return 0.40 + 0.50 * (offer_gross - lo) / (hi - lo)       # 0.40 at the minimum, 0.90 at the maximum
        return max(0.0, 0.40 - (lo - offer_gross) / lo)
    if hi is not None:
        if offer_gross >= hi * 1.05:
            return 1.0
        if offer_gross >= hi * 0.95:
            return 0.85
        return max(0.0, 0.50 - (hi - offer_gross) / hi)
    if lo is not None:
        if offer_gross >= lo * 1.25:
            return 1.0
        if offer_gross >= lo:
            return 0.75
        return max(0.0, 0.40 - (lo - offer_gross) / lo)
    return 0.55                                                        # no declared expectation


def acceptance_likelihood(need: NeedCtx, offer_salary_max: int, c: CandidateCtx,
                          now: datetime.datetime) -> Literal["low", "medium", "high"]:
    offer = to_gross(offer_salary_max, need.salary_type)
    if c.salary_min and offer < to_gross(c.salary_min, c.salary_type or "gross") * 0.75:
        return "low"
    salary = _salary_score(offer, c)
    conflict = bool(need.work_formats and c.work_formats and not set(need.work_formats) & set(c.work_formats))
    fmt = 0.8 if not need.work_formats or not c.work_formats else (0.0 if conflict else 1.0)
    if c.last_active_at is None:
        recency = 0.4
    else:
        seen = c.last_active_at if c.last_active_at.tzinfo else c.last_active_at.replace(tzinfo=datetime.timezone.utc)
        ref = now if now.tzinfo else now.replace(tzinfo=datetime.timezone.utc)
        days = max(0.0, (ref - seen).total_seconds() / 86400.0)
        recency = 1.0 if days <= 7 else 0.75 if days <= 30 else 0.5 if days <= 60 else 0.25
    status = {"confirmed": 1.0, "pending": 0.7}.get(c.league_status, 0.5)
    total = 0.40 * salary + 0.25 * fmt + 0.20 * recency + 0.15 * status
    if conflict:
        return "low" if total < 0.45 else "medium"
    return "high" if total >= 0.78 else "medium" if total >= 0.45 else "low"
