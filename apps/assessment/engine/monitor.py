"""Leak and drift monitor + IRT recalibration (ML-11, AI-13). Pure: no Django, no ORM, no core.enums.

Input: the families' authored parameters and their administered responses, each with the session's
θ̂, its standard error and the correctness of the answer.

1. Expected rates. A response's expected probability is E[P(θ)] under N(θ̂, SE²) (9-point
   Gauss–Hermite), not P(θ̂): θ̂ is an estimate, and plugging it in made about 15 % of correctly
   specified families look drifted in simulation (ML-11 review). With SE = 0 it is P(θ̂).
2. Tests per family, one-sided normal approximations on observed − expected counts:
   - leak: more correct than expected among examinees *below the item* (bands whose midpoint is
     under b) and overall. A leaked key helps exactly the people who could not solve the item.
   - drift: fewer correct than expected in any band or overall (the item got harder or broke).
   Within a family the tests are Bonferroni-combined; across families `monitor_families` controls
   the false discovery rate (Benjamini–Hochberg, q = 0.05), because ~50 families are tested on
   every run.
3. Recalibration: MAP (a, b) with c fixed and θ̂ taken as known, a lognormal prior on a (sd 0.5 on
   ln a) and a normal prior on b (sd 1.5) centred on the authored values; Fisher scoring with step
   halving until the step is below 1e-6. Standard errors come from the posterior information.
   girth is not used (it is not a dependency); fixed-θ MAP is what a monitor with a θ̂ per session
   needs. Parameter recovery is measured in validation (ML-8).
4. Status (a recommendation; BE decides what to apply and when):
   - retired: calibrated a is below 0.6 with confidence (upper 95 % bound < 0.6) on at least
     MIN_CALIBRATION_N responses ("a < 0.6 after calibration", ARCHITECTURE §2.5);
   - flagged: leak or drift after FDR control, an authored a < 0.6, or a calibration that did not
     converge;
   - active otherwise.
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
STATUSES: tuple[str, ...] = ("active", "flagged", "retired")

# θ bands of the four grades; the cuts equal content/grades.yaml (tests/ml/test_monitor.py checks).
BAND_CUTS: tuple[tuple[str, float, float], ...] = (
    ("intern", -4.0, -1.0),
    ("junior", -1.0, 0.0),
    ("middle", 0.0, 1.0),
    ("senior", 1.0, 4.0),
)
MIN_BAND_N = 20              # a band test needs this many responses (normal approximation)
MIN_GLOBAL_N = 30
MIN_CALIBRATION_N = 200      # ARCHITECTURE §2.12: recalibrate after about 200 responses
RETIRE_A = 0.6
FDR_Q = 0.05
ALPHA_SINGLE = 0.001         # per-test level when one family is analysed on its own
PRIOR_SD_LOG_A = 0.5
PRIOR_SD_B = 1.5
EPS = 1e-9

_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(9)
_GH_W = _GH_W / _GH_W.sum()


@dataclass(frozen=True)
class ItemResponse:
    family_id: str
    theta: float
    correct: bool
    se: float = 0.0              # SE of the session's θ̂; 0 treats θ̂ as exact
    session_id: str = ""         # for exposure as a share of sessions


@dataclass(frozen=True)
class BandStat:
    band: str
    theta_min: float
    theta_max: float
    n: int
    observed_rate: float
    expected_rate: float
    z_score: float


@dataclass(frozen=True)
class Calibration:
    a: float
    b: float
    se_a: float
    se_b: float
    converged: bool
    iterations: int


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
    calibrated_se_a: float | None = None
    calibrated_se_b: float | None = None
    calibration_converged: bool | None = None
    p_leak: float = 1.0          # family-level p-values (Bonferroni over its tests)
    p_drift: float = 1.0
    topic: str = ""
    specs: tuple[str, ...] = ()
    format: str = ""
    time_limit_s: int = 120
    exposure_rate: float = 0.0

    @property
    def drift_flag(self) -> bool:
        return "content_drift" in self.flags or "leak_suspected" in self.flags

    def to_dict(self) -> dict[str, Any]:
        def r(x, k):
            return round(float(x), k) if x is not None else None
        return {
            "id": self.family_id,
            "topic": self.topic,
            "specs": list(self.specs),
            "format": self.format,
            "time_limit_s": self.time_limit_s,
            "a": r(self.a, 3),
            "b": r(self.b, 3),
            "c": r(self.c, 3),
            "exposures": int(self.exposures),
            "exposure_rate": r(self.exposure_rate, 4),
            "observed_rate": r(self.observed_rate, 4),
            "expected_rate": r(self.expected_rate, 4),
            "drift_flag": self.drift_flag,
            "status": self.status,
            "flags": list(self.flags),
            "p_leak": r(self.p_leak, 6),
            "p_drift": r(self.p_drift, 6),
            "calibrated_a": r(self.calibrated_a, 3),
            "calibrated_b": r(self.calibrated_b, 3),
            "calibrated_se_a": r(self.calibrated_se_a, 3),
            "calibrated_se_b": r(self.calibrated_se_b, 3),
            "calibration_converged": self.calibration_converged,
            "bands": [
                {"band": bs.band, "theta_min": bs.theta_min, "theta_max": bs.theta_max, "n": bs.n,
                 "observed_rate": round(float(bs.observed_rate), 4),
                 "expected_rate": round(float(bs.expected_rate), 4), "z_score": round(float(bs.z_score), 2)}
                for bs in self.bands
            ],
        }


# ── statistics ─────────────────────────────────────────────────────────────

def expected_p(thetas: np.ndarray, ses: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    """E[P(θ)] for θ ~ N(θ̂, SE²), by 9-point Gauss–Hermite quadrature."""
    nodes = thetas[:, None] + ses[:, None] * _GH_X[None, :]
    return np.asarray(p_3pl(nodes, a, b, c), dtype=float) @ _GH_W


def _z(u: np.ndarray, p: np.ndarray) -> float:
    var = float(np.sum(p * (1.0 - p)))
    return float((u.sum() - p.sum()) / math.sqrt(var)) if var > 0 else 0.0


def _upper_tail(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def benjamini_hochberg(pvalues: Sequence[float], q: float = FDR_Q) -> list[bool]:
    """Which hypotheses are rejected at false discovery rate q (step-up procedure)."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: (pvalues[i], i))
    cutoff = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= q * rank / m:
            cutoff = rank
    rejected = [False] * m
    for rank, i in enumerate(order, start=1):
        rejected[i] = rank <= cutoff
    return rejected


# ── recalibration ──────────────────────────────────────────────────────────

def _log_posterior(alpha: float, b: float, thetas, u, c: float, prior_a: float, prior_b: float) -> float:
    p = np.clip(p_3pl(thetas, math.exp(alpha), b, c), EPS, 1.0 - EPS)
    ll = float(np.sum(u * np.log(p) + (1.0 - u) * np.log(1.0 - p)))
    return (ll - 0.5 * ((alpha - math.log(prior_a)) / PRIOR_SD_LOG_A) ** 2
            - 0.5 * ((b - prior_b) / PRIOR_SD_B) ** 2)


def _score_info(alpha, b, thetas, u, c, prior_a, prior_b):
    """Gradient and expected information of the log posterior in (ln a, b)."""
    a = math.exp(alpha)
    sig = 1.0 / (1.0 + np.exp(-np.clip(a * (thetas - b), -30.0, 30.0)))
    p = np.clip(c + (1.0 - c) * sig, EPS, 1.0 - EPS)
    dp = (1.0 - c) * sig * (1.0 - sig)
    g_alpha = dp * a * (thetas - b)              # dP / d(ln a)
    g_b = -dp * a                                # dP / db
    w = 1.0 / (p * (1.0 - p))
    prec = np.diag([1.0 / PRIOR_SD_LOG_A ** 2, 1.0 / PRIOR_SD_B ** 2])
    score = np.array([np.sum(w * (u - p) * g_alpha), np.sum(w * (u - p) * g_b)])
    score -= prec @ np.array([alpha - math.log(prior_a), b - prior_b])
    info = np.array([[np.sum(w * g_alpha ** 2), np.sum(w * g_alpha * g_b)],
                     [np.sum(w * g_alpha * g_b), np.sum(w * g_b ** 2)]]) + prec
    return score, info


def recalibrate_family(thetas, u, c: float, prior_a: float = 1.0, prior_b: float = 0.0,
                       max_iter: int = 100, tol: float = 1e-6) -> Calibration:
    """MAP (a, b) of a 3PL item with fixed c and known abilities: Fisher scoring in (ln a, b), the
    step halved until the log posterior does not decrease. `converged` is False if the step never
    got below `tol` within `max_iter` iterations. Bounds: a in [0.1, 5], b in [-5, 5]."""
    thetas = np.asarray(thetas, dtype=float)
    u = np.asarray(u, dtype=float)
    alpha, b = math.log(prior_a), float(prior_b)
    current = _log_posterior(alpha, b, thetas, u, c, prior_a, prior_b)
    converged, it = False, 0
    for _ in range(max_iter):
        it += 1
        score, info = _score_info(alpha, b, thetas, u, c, prior_a, prior_b)
        step = np.linalg.solve(info, score)
        scale = 1.0
        while True:
            na = min(max(alpha + scale * step[0], math.log(0.1)), math.log(5.0))
            nb = min(max(b + scale * step[1], -5.0), 5.0)
            value = _log_posterior(na, nb, thetas, u, c, prior_a, prior_b)
            if value >= current - 1e-12 or scale < 1e-6:
                break
            scale *= 0.5
        moved = max(abs(na - alpha), abs(nb - b))
        alpha, b, current = na, nb, value
        if moved < tol:
            converged = True
            break
    _, info = _score_info(alpha, b, thetas, u, c, prior_a, prior_b)
    cov = np.linalg.inv(info)
    a = math.exp(alpha)
    return Calibration(a=a, b=b, se_a=a * math.sqrt(max(float(cov[0, 0]), 0.0)),
                       se_b=math.sqrt(max(float(cov[1, 1]), 0.0)), converged=converged, iterations=it)


# ── per family ─────────────────────────────────────────────────────────────

def _band_mask(thetas: np.ndarray, k: int) -> np.ndarray:
    _, lo, hi = BAND_CUTS[k]
    lower = thetas >= lo if k > 0 else np.ones(thetas.shape, dtype=bool)
    upper = thetas < hi if k < len(BAND_CUTS) - 1 else np.ones(thetas.shape, dtype=bool)
    return lower & upper


def analyze_family(meta: FamilyMeta, responses: Sequence[ItemResponse]) -> FamilyDriftReport:
    """Rates, band statistics, family-level p-values and the calibration for one family. Flags are
    set at ALPHA_SINGLE here; `monitor_families` re-decides them with FDR control over the pool."""
    rows = [r for r in responses if r.family_id == meta.id]
    rep = FamilyDriftReport(family_id=meta.id, a=meta.a, b=meta.b, c=meta.c, exposures=len(rows),
                            observed_rate=0.0, expected_rate=0.0, bands=[], topic=meta.topic,
                            specs=meta.specs, format=meta.format, time_limit_s=meta.time_limit_s)
    if rows:
        thetas = np.array([r.theta for r in rows], dtype=float)
        ses = np.array([max(r.se, 0.0) for r in rows], dtype=float)
        u = np.array([1.0 if r.correct else 0.0 for r in rows], dtype=float)
        p = expected_p(thetas, ses, meta.a, meta.b, meta.c)
        rep.observed_rate, rep.expected_rate = float(u.mean()), float(p.mean())
        leak_p, drift_p = [], []
        for k, (name, lo, hi) in enumerate(BAND_CUTS):
            mask = _band_mask(thetas, k)
            n = int(mask.sum())
            if not n:
                rep.bands.append(BandStat(name, lo, hi, 0, 0.0, 0.0, 0.0))
                continue
            z = _z(u[mask], p[mask])
            rep.bands.append(BandStat(name, lo, hi, n, float(u[mask].mean()), float(p[mask].mean()), z))
            if n >= MIN_BAND_N:
                drift_p.append(_upper_tail(-z))
                if (lo + hi) / 2 < meta.b:               # examinees below the item: a leak shows here
                    leak_p.append(_upper_tail(z))
        if len(rows) >= MIN_GLOBAL_N:
            z = _z(u, p)
            leak_p.append(_upper_tail(z))
            drift_p.append(_upper_tail(-z))
        rep.p_leak = min(1.0, min(leak_p) * len(leak_p)) if leak_p else 1.0
        rep.p_drift = min(1.0, min(drift_p) * len(drift_p)) if drift_p else 1.0
        if len(rows) >= MIN_CALIBRATION_N and 0 < u.sum() < len(u):
            cal = recalibrate_family(thetas, u, meta.c, prior_a=meta.a, prior_b=meta.b)
            rep.calibrated_a, rep.calibrated_b = cal.a, cal.b
            rep.calibrated_se_a, rep.calibrated_se_b = cal.se_a, cal.se_b
            rep.calibration_converged = cal.converged
    _decide(rep, rep.p_leak <= ALPHA_SINGLE, rep.p_drift <= ALPHA_SINGLE)
    return rep


def _decide(rep: FamilyDriftReport, leak: bool, drift: bool) -> None:
    flags = []
    if leak:
        flags.append("leak_suspected")
    if drift:
        flags.append("content_drift")
    if rep.a < RETIRE_A:
        flags.append("low_discrimination_prior")         # authored a: review, do not retire
    if rep.calibration_converged is False:
        flags.append("calibration_not_converged")
    low_a = bool(rep.calibrated_a is not None and rep.calibration_converged
                 and rep.calibrated_a + 1.96 * (rep.calibrated_se_a or 0.0) < RETIRE_A)
    if low_a:
        flags.append("low_discrimination")
    rep.flags = flags
    rep.status = "retired" if low_a else ("flagged" if flags else "active")


def monitor_families(metas: Sequence[FamilyMeta], responses: Sequence[ItemResponse],
                     q: float = FDR_Q) -> list[FamilyDriftReport]:
    """Monitor a pool. Leak and drift are decided with Benjamini–Hochberg over all families and both
    tests. Exposure is the share of sessions that saw the family when session ids are given, else
    the share of responses. Sorted retired → flagged → active, then by exposures, then by id."""
    by_family: dict[str, list[ItemResponse]] = {}
    for r in responses:
        by_family.setdefault(r.family_id, []).append(r)
    reports = [analyze_family(m, by_family.get(m.id, [])) for m in metas]

    rejected = benjamini_hochberg([rep.p_leak for rep in reports] + [rep.p_drift for rep in reports], q)
    for i, rep in enumerate(reports):
        _decide(rep, rejected[i], rejected[len(reports) + i])

    sessions = {r.session_id for r in responses if r.session_id}
    for rep in reports:
        rows = by_family.get(rep.family_id, [])
        if sessions:
            rep.exposure_rate = len({r.session_id for r in rows if r.session_id}) / len(sessions)
        else:
            rep.exposure_rate = rep.exposures / len(responses) if responses else 0.0
    order = {"retired": 0, "flagged": 1, "active": 2}
    reports.sort(key=lambda rep: (order[rep.status], -rep.exposures, rep.family_id))
    return reports
