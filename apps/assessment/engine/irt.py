"""3PL IRT with fixed guessing, Fisher information and EAP on a 61-point grid (ML-3).

Logistic metric (D = 1): P(θ) = c + (1 − c) / (1 + e^(−a(θ − b))).
EAP uses a neutral N(0, 1) prior on 61 equally spaced points over [−4, 4], computed in log space
with max-subtraction; SE is the posterior standard deviation. Probabilities like P(θ ≥ cut)
come from the same posterior grid, so θ̂, SE and the policy probabilities always agree.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

GRID = np.linspace(-4.0, 4.0, 61)
_LOG_PRIOR = -0.5 * GRID ** 2 - math.log(float(np.exp(-0.5 * GRID ** 2).sum()))
EPS = 1e-9

Item = tuple[float, float, float]      # (a, b, c)


def p_3pl(theta, a: float, b: float, c: float):
    """P(correct | θ); θ may be a scalar or an array."""
    return c + (1.0 - c) / (1.0 + np.exp(-a * (np.asarray(theta, dtype=float) - b)))


def information(theta, a: float, b: float, c: float):
    """Fisher information a² · (Q/P) · ((P − c)/(1 − c))²."""
    p = np.clip(p_3pl(theta, a, b, c), EPS, 1.0 - EPS)
    return a * a * ((1.0 - p) / p) * ((p - c) / (1.0 - c)) ** 2


def log_likelihood(items: Sequence[Item], responses: Sequence[bool]) -> np.ndarray:
    """Σ log P(u | θ) over the grid."""
    if len(items) != len(responses):
        raise ValueError("items and responses differ in length")
    ll = np.zeros_like(GRID)
    if not items:
        return ll
    arr = np.asarray(items, dtype=float)
    a, b, c = arr[:, 0:1], arr[:, 1:2], arr[:, 2:3]
    p = np.clip(c + (1.0 - c) / (1.0 + np.exp(-a * (GRID[None, :] - b))), EPS, 1.0 - EPS)
    u = np.asarray(responses, dtype=bool)[:, None]
    return np.where(u, np.log(p), np.log1p(-p)).sum(axis=0)


def posterior(items: Sequence[Item], responses: Sequence[bool],
              prior_mean: float = 0.0, prior_sd: float = 1.0) -> np.ndarray:
    """Normalised posterior weights on GRID. Scoring always uses the neutral N(0, 1) prior; the
    prior parameters exist for analysis (e.g. validation of shrinkage), never for a grade."""
    if prior_mean == 0.0 and prior_sd == 1.0:
        log_prior = _LOG_PRIOR
    else:
        log_prior = -0.5 * ((GRID - prior_mean) / prior_sd) ** 2
    lp = log_prior + log_likelihood(items, responses)
    w = np.exp(lp - lp.max())
    return w / w.sum()


def eap(items: Sequence[Item], responses: Sequence[bool]) -> tuple[float, float]:
    """(θ̂, SE) = posterior mean and SD under the neutral prior."""
    post = posterior(items, responses)
    return moments(post)


def moments(post: np.ndarray) -> tuple[float, float]:
    theta = float((GRID * post).sum())
    se = float(math.sqrt(max(0.0, float(((GRID - theta) ** 2 * post).sum()))))
    return theta, se


STEP = float(GRID[1] - GRID[0])


def prob_at_least(post: np.ndarray, cut: float) -> float:
    """P(θ ≥ cut | data) from the posterior grid.

    Each grid point carries the mass of a bin of width STEP centred on it; a bin the cut splits
    contributes the share above the cut. So a cut on a grid point counts half of that point,
    and the answer moves continuously with the cut instead of jumping between grid points.
    """
    frac = np.clip((GRID + STEP / 2 - cut) / STEP, 0.0, 1.0)
    return float((post * frac).sum())
