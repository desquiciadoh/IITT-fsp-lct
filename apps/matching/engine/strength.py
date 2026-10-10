"""Profile Strength, FSP boost and league percentiles (ML-4; ARCHITECTURE §2.6).

    Strength  = min(100, 0.85 · Base + FSP Boost)                      0..100
    Base      = 0.75 · θ-percentile + 0.15 · 100 · activity + 0.10 · 100 · freshness
    activity  = 1 − exp(−Σ 0.5^(age_days / 90))   over accepted micro-tasks (90-day half-life)
    freshness = 0.5^(days since last activity / 30)                    0 when never active
    FSP Boost = 12 · (1 − e^(−R/2)) + rank bonus                       0..15
    R         = Σ placement weights (winner 1.0, prize-winner 0.7, finalist 0.4) + min(0.6, 0.15 · participations)
    rank bonus: cat1 +1, KMS +2, MS +3 (cat2/cat3 0)

All five FSP disciplines weigh the same (QA). FSP changes Strength and ranking, never the
grade (invariant 4). The boost is a pure function of the *set* of results: duplicates from a
re-sync count once and results dated after `now` are ignored, so recomputing is idempotent.
"""
from __future__ import annotations

import bisect
import datetime
import math
from collections.abc import Sequence
from dataclasses import dataclass

from .types import CandidateCtx, FspResultCtx

PLACEMENT_WEIGHTS = {"winner": 1.0, "prize_winner": 0.7, "finalist": 0.4, "participant": 0.15}
PARTICIPATION_CAP = 0.6
RANK_BONUS = {"cat1": 1.0, "kms": 2.0, "ms": 3.0}
BOOST_SCALE = 12.0
ACTIVITY_HALF_LIFE_DAYS = 90.0
FRESHNESS_HALF_LIFE_DAYS = 30.0
W_PERCENTILE, W_ACTIVITY, W_FRESHNESS = 0.75, 0.15, 0.10
BASE_SHARE = 0.85


@dataclass(frozen=True)
class StrengthBreakdown:
    base: float
    fsp_boost: float
    total: float
    percentile: float


def _to_date(now: datetime.datetime | datetime.date) -> datetime.date:
    return now.date() if isinstance(now, datetime.datetime) else now


def placement_sum(results: Sequence[FspResultCtx], now: datetime.datetime) -> float:
    """R: placements count in full, participation-only credit is capped at 0.6."""
    today = _to_date(now)
    distinct = sorted(set(results), key=lambda r: (r.date, r.tier, r.discipline, r.participants_total,
                                                   r.team_size or 0))
    placed = participated = 0.0
    for r in distinct:
        if r.date > today:
            continue
        if r.tier not in PLACEMENT_WEIGHTS:
            raise ValueError(f"unknown placement tier: {r.tier!r}")
        if r.tier == "participant":
            participated += PLACEMENT_WEIGHTS["participant"]
        else:
            placed += PLACEMENT_WEIGHTS[r.tier]
    return placed + min(PARTICIPATION_CAP, participated)


def fsp_boost(rank: str | None, results: Sequence[FspResultCtx], now: datetime.datetime) -> float:
    """0..15; no FSP history -> 0."""
    r = placement_sum(results, now)
    return BOOST_SCALE * (1.0 - math.exp(-r / 2.0)) + RANK_BONUS.get(rank or "", 0.0)


def activity(microtask_dates: Sequence[datetime.date], now: datetime.datetime) -> float:
    """0..1 from accepted micro-tasks, each decaying with a 90-day half-life."""
    today = _to_date(now)
    # one entry per accepted task: several tasks on one day all count (dates are not identities)
    s = sum(0.5 ** ((today - d).days / ACTIVITY_HALF_LIFE_DAYS) for d in sorted(microtask_dates)
            if d <= today)
    return 1.0 - math.exp(-s)


def freshness(last_active_at: datetime.datetime | None, now: datetime.datetime) -> float:
    """0..1, halves every 30 days since the last activity; never active -> 0."""
    if last_active_at is None:
        return 0.0
    days = max(0.0, (now - last_active_at).total_seconds() / 86400.0)
    return 0.5 ** (days / FRESHNESS_HALF_LIFE_DAYS)


def percentiles(thetas: Sequence[float]) -> list[float]:
    """Mid-rank percentile of each θ in its league, 0..100, same order as the input.

    pct = 100 · (#below + 0.5 · #equal) / N, so ties share one value and a single member gets 50.
    """
    if not all(math.isfinite(t) for t in thetas):
        raise ValueError("percentiles() needs finite θ values; BE drops members without θ")
    order = sorted(thetas)
    return [percentile_of(t, order, presorted=True) for t in thetas]


def percentile_of(theta: float, thetas: Sequence[float], presorted: bool = False) -> float:
    """Mid-rank percentile of `theta` among `thetas` (the league, the candidate included)."""
    if not thetas:
        return 0.0
    if not math.isfinite(theta) or not all(math.isfinite(t) for t in thetas):
        raise ValueError("percentile_of() needs finite θ values")
    order = thetas if presorted else sorted(thetas)
    below = bisect.bisect_left(order, theta)
    equal = bisect.bisect_right(order, theta) - below
    return 100.0 * (below + 0.5 * equal) / len(order)


def strength(c: CandidateCtx, league_thetas: Sequence[float], now: datetime.datetime) -> StrengthBreakdown:
    """Strength of a league member. `league_thetas` are the θ of every member, the candidate included."""
    pct = percentile_of(c.theta, league_thetas) if c.theta is not None and league_thetas else 0.0
    base = (W_PERCENTILE * pct + W_ACTIVITY * 100.0 * activity(c.microtask_dates, now)
            + W_FRESHNESS * 100.0 * freshness(c.last_active_at, now))
    boost = fsp_boost(c.fsp_rank, c.fsp_results, now)
    return StrengthBreakdown(base=base, fsp_boost=boost, total=min(100.0, BASE_SHARE * base + boost),
                             percentile=pct)
