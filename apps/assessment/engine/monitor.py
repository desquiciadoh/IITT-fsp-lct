"""Leak and drift monitor + IRT recalibration (ML-11, AI-13).

Pure engine module: no Django, no ORM, no core.enums.

Monitors item families against administered response data:
1. Groups candidate responses into θ ability bands (intern, junior, middle, senior).
2. Computes observed vs expected correct rate under the 3PL IRT model and standardized residuals.
3. Detects anomalies:
   - "leak_suspected": observed significantly exceeds expected (z >= 2.5 in lower bands or overall).
   - "content_drift": observed significantly below expected (z <= -2.5).
   - "low_discrimination": discrimination parameter a < 0.6.
4. Recommends family lifecycle status:
   - "active": normal performance.
   - "flagged": drift or leak suspected.
   - "retired": low discrimination (a < 0.6) or persistent corruption.
5. IRT Recalibration:
   Estimates updated (a, b) parameters from response data via MAP estimation under 3PL with fixed c.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from ..families.base import FamilyMeta
from .irt import p_3pl

Status = Literal["active", "flagged", "retired"]

# θ cuts separating the 4 grade bands (ARCHITECTURE §2.5, ML-2, D7)
BAND_CUTS: tuple[tuple[str, float, float], ...] = (
    ("intern", -4.0, -1.0),
    ("junior", -1.0, 0.0),
    ("middle", 0.0, 1.0),
    ("senior", 1.0, 4.0),
)

EPS = 1e-9


@dataclass(frozen=True)
class ItemResponse:
    family_id: str
    theta: float
    correct: bool


@dataclass(frozen=True)
class BandStat:
    band: str
    theta_min: float
    theta_max: float
    n: int
    observed_rate: float
    expected_rate: float
    z_score: float


@dataclass
class FamilyDriftReport:
    family_id: str
    a: float
    b: float
    c: float
    exposures: int
    observed_rate: float
    expected_rate: float
    bands: list[BandStat]
    flags: list[str] = field(default_factory=list)
    status: Status = "active"
    calibrated_a: float | None = None
    calibrated_b: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.family_id,
            "a": round(float(self.a), 3),
            "b": round(float(self.b), 3),
            "c": round(float(self.c), 3),
            "exposures": int(self.exposures),
            "observed_rate": round(float(self.observed_rate), 4),
            "expected_rate": round(float(self.expected_rate), 4),
            "status": self.status,
            "flags": list(self.flags),
            "calibrated_a": round(float(self.calibrated_a), 3) if self.calibrated_a is not None else None,
            "calibrated_b": round(float(self.calibrated_b), 3) if self.calibrated_b is not None else None,
            "bands": [
                {
                    "band": bs.band,
                    "theta_min": bs.theta_min,
                    "theta_max": bs.theta_max,
                    "n": bs.n,
                    "observed_rate": round(float(bs.observed_rate), 4),
                    "expected_rate": round(float(bs.expected_rate), 4),
                    "z_score": round(float(bs.z_score), 2),
                }
                for bs in self.bands
            ],
        }


def analyze_family(
    meta: FamilyMeta,
    responses: Sequence[ItemResponse],
    min_band_samples: int = 5,
) -> FamilyDriftReport:
    """Analyze observed vs expected performance of a single family across theta bands."""
    family_resps = [r for r in responses if r.family_id == meta.id]
    n_total = len(family_resps)

    if not n_total:
        status: Status = "retired" if meta.a < 0.6 else "active"
        flags = ["low_discrimination"] if meta.a < 0.6 else []
        return FamilyDriftReport(
            family_id=meta.id,
            a=meta.a,
            b=meta.b,
            c=meta.c,
            exposures=0,
            observed_rate=0.0,
            expected_rate=0.0,
            bands=[],
            flags=flags,
            status=status,
            calibrated_a=meta.a,
            calibrated_b=meta.b,
        )

    thetas = np.array([r.theta for r in family_resps], dtype=float)
    u = np.array([1.0 if r.correct else 0.0 for r in family_resps], dtype=float)

    # 3PL probabilities for all respondents
    probs = np.clip(p_3pl(thetas, meta.a, meta.b, meta.c), EPS, 1.0 - EPS)
    observed_rate = float(np.mean(u))
    expected_rate = float(np.mean(probs))

    band_stats: list[BandStat] = []
    flags: list[str] = []

    for band_name, th_lo, th_hi in BAND_CUTS:
        mask = (thetas >= th_lo) & (thetas < th_hi) if th_hi < 4.0 else (thetas >= th_lo)
        n_band = int(np.sum(mask))
        if n_band == 0:
            band_stats.append(BandStat(band_name, th_lo, th_hi, 0, 0.0, 0.0, 0.0))
            continue

        u_band = u[mask]
        p_band = probs[mask]
        obs_b = float(np.mean(u_band))
        exp_b = float(np.mean(p_band))

        var_sum = float(np.sum(p_band * (1.0 - p_band)))
        std_err = math.sqrt(var_sum) / n_band if var_sum > 0 else 1e-6
        z_score = (obs_b - exp_b) / std_err

        band_stats.append(BandStat(band_name, th_lo, th_hi, n_band, obs_b, exp_b, z_score))

        # Check anomalies if sample size in band is adequate
        if n_band >= min_band_samples:
            if band_name in ("intern", "junior") and z_score >= 2.5:
                # Lower ability groups answering unexpectedly well -> leak indicator
                if "leak_suspected" not in flags:
                    flags.append("leak_suspected")
            elif z_score <= -2.5:
                # Group scoring significantly worse than expected -> drift indicator
                if "content_drift" not in flags:
                    flags.append("content_drift")

    # Global check: if total observed rate deviates dramatically
    var_total = float(np.sum(probs * (1.0 - probs)))
    se_total = math.sqrt(var_total) / n_total if var_total > 0 else 1e-6
    z_total = (observed_rate - expected_rate) / se_total

    if n_total >= 20:
        if z_total >= 3.0 and "leak_suspected" not in flags:
            flags.append("leak_suspected")
        elif z_total <= -3.0 and "content_drift" not in flags:
            flags.append("content_drift")

    # Recalibrate (a, b)
    cal_a, cal_b = recalibrate_family(thetas, u, meta.c, prior_a=meta.a, prior_b=meta.b)

    # Check discrimination threshold
    if meta.a < 0.6:
        if "low_discrimination" not in flags:
            flags.append("low_discrimination")
    elif cal_a < 0.6 and "leak_suspected" not in flags:
        # If no leak is suspected but calibrated discrimination is under 0.6, retire
        if "low_discrimination" not in flags:
            flags.append("low_discrimination")

    # Determine recommended status
    if "low_discrimination" in flags:
        status = "retired"
    elif flags:
        status = "flagged"
    else:
        status = "active"

    return FamilyDriftReport(
        family_id=meta.id,
        a=meta.a,
        b=meta.b,
        c=meta.c,
        exposures=n_total,
        observed_rate=observed_rate,
        expected_rate=expected_rate,
        bands=band_stats,
        flags=flags,
        status=status,
        calibrated_a=cal_a,
        calibrated_b=cal_b,
    )


def recalibrate_family(
    thetas: np.ndarray,
    u: np.ndarray,
    c: float,
    prior_a: float = 1.0,
    prior_b: float = 0.0,
    max_iter: int = 25,
) -> tuple[float, float]:
    """MAP estimation of (a, b) for a 3PL item with fixed c.

    Maximizes: log L(a, b) - 0.5 * ((ln a - ln prior_a)/0.5)^2 - 0.5 * ((b - prior_b)/1.5)^2.
    Bounded to a in [0.2, 3.5] and b in [-3.5, 3.5].
    """
    if len(thetas) < 5 or np.all(u == 0) or np.all(u == 1):
        return float(prior_a), float(prior_b)

    a = float(np.clip(prior_a, 0.4, 2.5))
    b = float(np.clip(prior_b, -2.5, 2.5))
    lr = 0.1

    for _ in range(max_iter):
        z = a * (thetas - b)
        sig = 1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0)))
        p = np.clip(c + (1.0 - c) * sig, EPS, 1.0 - EPS)

        # Gradient of log-likelihood
        # dp/da = (1-c) * sig * (1-sig) * (thetas - b)
        # dp/db = -a * (1-c) * sig * (1-sig)
        common = (1.0 - c) * sig * (1.0 - sig)
        weight = (u - p) / (p * (1.0 - p))

        grad_a = np.sum(weight * common * (thetas - b))
        grad_b = np.sum(weight * common * (-a))

        # Prior penalties: lognormal prior on a, normal prior on b
        prior_grad_a = -(math.log(max(EPS, a)) - math.log(max(EPS, prior_a))) / (0.25 * a)
        prior_grad_b = -(b - prior_b) / 2.25

        total_grad_a = grad_a + prior_grad_a
        total_grad_b = grad_b + prior_grad_b

        # Gradient step with clipping
        a += float(np.clip(lr * total_grad_a, -0.3, 0.3))
        b += float(np.clip(lr * total_grad_b, -0.3, 0.3))

        a = float(np.clip(a, 0.2, 3.5))
        b = float(np.clip(b, -3.5, 3.5))

    return a, b


def monitor_families(
    metas: Sequence[FamilyMeta],
    responses: Sequence[ItemResponse],
) -> list[FamilyDriftReport]:
    """Run leak and drift monitoring over a pool of item families."""
    resp_by_fam: dict[str, list[ItemResponse]] = {}
    for r in responses:
        resp_by_fam.setdefault(r.family_id, []).append(r)

    reports = []
    for meta in metas:
        resps = resp_by_fam.get(meta.id, [])
        report = analyze_family(meta, resps)
        reports.append(report)

    # Sort reports by status (retired -> flagged -> active), then exposures desc, then family id
    status_order = {"retired": 0, "flagged": 1, "active": 2}
    reports.sort(key=lambda rep: (status_order.get(rep.status, 3), -rep.exposures, rep.family_id))
    return reports
