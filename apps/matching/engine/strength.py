"""Profile Strength, FSP boost and league percentiles (ML.md §3). ML-0: stub boost, real percentiles."""
from __future__ import annotations

import bisect
import datetime
import math
from collections.abc import Sequence
from dataclasses import dataclass

from .types import CandidateCtx, FspResultCtx


@dataclass(frozen=True)
class StrengthBreakdown:
    base: float
    fsp_boost: float
    total: float
    percentile: float


def fsp_boost(rank: str | None, results: Sequence[FspResultCtx], now: datetime.datetime) -> float:
    """0..15. Stub: 5 points per distinct result, capped."""
    return float(min(15, 5 * len(set(results))))


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
    """Stub: base = θ-percentile, total = 0.85·base + boost. `league_thetas` includes the candidate."""
    pct = percentile_of(c.theta, league_thetas) if c.theta is not None else 0.0
    base = pct
    boost = fsp_boost(c.fsp_rank, c.fsp_results, now)
    return StrengthBreakdown(base=base, fsp_boost=boost, total=min(100.0, 0.85 * base + boost),
                             percentile=pct)
