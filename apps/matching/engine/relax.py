"""Counterfactual relaxations and acceptance likelihood (ML-10, AI-12).

Pure engine module: no Django, no ORM, no core.enums.

Relaxations:
  Evaluates actionable counterfactual changes to a hiring need (removing a must-have skill,
  allowing adjacent grades, adding remote/hybrid formats, expanding salary budget) and counts
  how many additional candidates qualify (delta > 0). Returns the top 3 relaxations sorted by delta desc.

Acceptance likelihood:
  Estimates low/medium/high probability that a candidate will accept a draft offer based on:
  1. Salary ratio: offer_salary_max vs candidate's expectations (both in gross).
  2. Format fit: overlap between candidate work formats and need work formats.
  3. League status: confirmed vs unconfirmed / pending.
  4. Responsiveness: activity freshness from last_active_at.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .features import direct_evidence, skill_name
from .salary import to_gross
from .score import passes_hard_filters
from .types import CandidateCtx, NeedCtx, Weights

FORMAT_RU: dict[str, str] = {
    "remote": "удалённый формат",
    "hybrid": "гибридный формат",
    "office": "офисный формат",
}


@dataclass(frozen=True)
class Relaxation:
    change: str     # e.g. "убрать Kubernetes из обязательных"
    delta: int      # +23 candidates


def _qualifies(need: NeedCtx, c: CandidateCtx) -> bool:
    """True if candidate passes hard filters, has evidence for all must-skills, and meets budget."""
    if not passes_hard_filters(need, c):
        return False

    # 1. Must-have skills: candidate must have direct evidence for all of them
    for s in need.must_skills:
        ev, _ = direct_evidence(c, s)
        if ev <= 0.0:
            return False

    # 2. Salary affordability: if candidate specifies salary_min, it shouldn't exceed budget max
    if c.salary_min is not None and need.salary_max > 0:
        c_min_gross = to_gross(c.salary_min, c.salary_type or "gross")
        need_max_gross = to_gross(need.salary_max, need.salary_type)
        if c_min_gross > need_max_gross * 1.05:
            return False

    return True


def relaxations(
    need: NeedCtx,
    pool: Sequence[CandidateCtx],
    weights: Weights | None = None,
) -> list[Relaxation]:
    """Top 3 counterfactual relaxations by delta candidates.

    Iterates through potential constraint relaxations:
    - Removing each must-have skill
    - Allowing adjacent grades
    - Adding omitted work formats (remote, hybrid, office)
    - Increasing salary budget by 20%
    """
    if not pool:
        return []

    base_count = sum(1 for c in pool if _qualifies(need, c))
    candidates: list[Relaxation] = []

    # 1. Relax must-have skills (one by one)
    for s in need.must_skills:
        rem_skills = tuple(x for x in need.must_skills if x != s)
        relaxed_need = dataclasses.replace(need, must_skills=rem_skills)
        count = sum(1 for c in pool if _qualifies(relaxed_need, c))
        delta = count - base_count
        if delta > 0:
            s_name = skill_name(s)
            candidates.append(Relaxation(change=f"убрать {s_name} из обязательных", delta=delta))

    # 2. Allow adjacent grades
    if not need.allow_adjacent:
        relaxed_need = dataclasses.replace(need, allow_adjacent=True)
        count = sum(1 for c in pool if _qualifies(relaxed_need, c))
        delta = count - base_count
        if delta > 0:
            candidates.append(Relaxation(change="разрешить смежные грейды", delta=delta))

    # 3. Add work formats
    if need.work_formats:
        for fmt in ("remote", "hybrid", "office"):
            if fmt not in need.work_formats:
                relaxed_need = dataclasses.replace(need, work_formats=tuple(list(need.work_formats) + [fmt]))
                count = sum(1 for c in pool if _qualifies(relaxed_need, c))
                delta = count - base_count
                if delta > 0:
                    label = FORMAT_RU.get(fmt, fmt)
                    candidates.append(Relaxation(change=f"добавить {label}", delta=delta))

    # 4. Increase budget by 20%
    if need.salary_max > 0:
        relaxed_need = dataclasses.replace(need, salary_max=int(round(need.salary_max * 1.20)))
        count = sum(1 for c in pool if _qualifies(relaxed_need, c))
        delta = count - base_count
        if delta > 0:
            candidates.append(Relaxation(change="увеличить бюджет на 20 %", delta=delta))

    # Sort by delta descending, tie-break by change text ascending
    candidates.sort(key=lambda r: (-r.delta, r.change))
    return candidates[:3]


def acceptance_likelihood(
    need: NeedCtx,
    offer_salary_max: int,
    c: CandidateCtx,
) -> Literal["low", "medium", "high"]:
    """Estimate probability (low, medium, high) of candidate accepting the offer.

    Evaluated axes:
    - Salary ratio (40% weight): offer_salary_max vs candidate expectations in gross.
    - Format fit (25% weight): candidate work_formats matching need work_formats.
    - Responsiveness (20% weight): days since last_active_at.
    - Status (15% weight): confirmed in league vs unconfirmed / pending.
    """
    # ── 1. Salary score (0..1) ────────────────────────────────────────────────
    offer_gross = to_gross(offer_salary_max, need.salary_type)
    c_max_gross = to_gross(c.salary_max, c.salary_type or "gross") if c.salary_max else None
    c_min_gross = to_gross(c.salary_min, c.salary_type or "gross") if c.salary_min else None

    if c_max_gross is not None and c_min_gross is not None and c_max_gross > c_min_gross:
        if offer_gross >= c_max_gross * 1.05:
            salary_score = 1.0
        elif offer_gross >= c_max_gross:
            salary_score = 0.90
        elif offer_gross >= c_min_gross:
            # Interpolate between min (0.40) and max (0.90)
            frac = (offer_gross - c_min_gross) / (c_max_gross - c_min_gross)
            salary_score = 0.40 + 0.50 * frac
        else:
            under_ratio = (c_min_gross - offer_gross) / c_min_gross
            salary_score = max(0.0, 0.40 - under_ratio)
    elif c_max_gross is not None:
        if offer_gross >= c_max_gross * 1.05:
            salary_score = 1.0
        elif offer_gross >= c_max_gross * 0.95:
            salary_score = 0.85
        else:
            under_ratio = (c_max_gross - offer_gross) / c_max_gross
            salary_score = max(0.0, 0.50 - under_ratio)
    elif c_min_gross is not None:
        if offer_gross >= c_min_gross * 1.25:
            salary_score = 1.0
        elif offer_gross >= c_min_gross:
            salary_score = 0.75
        else:
            under_ratio = (c_min_gross - offer_gross) / c_min_gross
            salary_score = max(0.0, 0.40 - under_ratio)
    else:
        # No declared salary expectations
        salary_score = 0.55

    # Hard drop if offer is heavily below candidate's minimum (> 25% below min)
    if c_min_gross and offer_gross < c_min_gross * 0.75:
        return "low"

    # ── 2. Format fit (0..1) ──────────────────────────────────────────────────
    has_format_conflict = False
    if not need.work_formats or not c.work_formats:
        format_score = 0.8
    else:
        common = set(need.work_formats) & set(c.work_formats)
        if common:
            format_score = 1.0
        else:
            format_score = 0.0
            has_format_conflict = True

    # ── 3. Responsiveness (0..1) ──────────────────────────────────────────────
    if c.last_active_at is None:
        resp_score = 0.4
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        act = c.last_active_at
        if act.tzinfo is None:
            act = act.replace(tzinfo=datetime.timezone.utc)
        days = max(0, (now - act).total_seconds() / 86400.0)
        if days <= 7:
            resp_score = 1.0
        elif days <= 30:
            resp_score = 0.75
        elif days <= 60:
            resp_score = 0.5
        else:
            resp_score = 0.25

    # ── 4. Status score (0..1) ────────────────────────────────────────────────
    if c.league_status == "confirmed":
        status_score = 1.0
    elif c.league_status == "pending":
        status_score = 0.7
    else:
        status_score = 0.5

    # Weighted combination
    total = (
        0.40 * salary_score
        + 0.25 * format_score
        + 0.20 * resp_score
        + 0.15 * status_score
    )

    if has_format_conflict:
        # Candidate and position have incompatible formats: cannot be "high"
        return "low" if total < 0.45 else "medium"

    if total >= 0.78:
        return "high"
    if total >= 0.45:
        return "medium"
    return "low"
