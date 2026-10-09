"""Reference IRT/CAT/ranking math for FSP Draft, used to cross-check production code.

Not production code: the engine lives in apps/assessment/engine/. Use this to compute golden values for
tests and to sanity-check a formula:  .venv/Scripts/python .claude/skills/irt-cat/scripts/irt_reference.py
"""
from __future__ import annotations

import math

import numpy as np

GRID = np.linspace(-4.0, 4.0, 61)              # 61-point quadrature, step 0.1333
PRIOR = np.exp(-0.5 * GRID**2)
PRIOR /= PRIOR.sum()                            # N(0,1) prior weights on the grid
EPS = 1e-9


def p3pl(theta, a, b, c):
    """P(correct | θ) = c + (1 − c) / (1 + exp(−a(θ − b))). Logistic metric (D = 1)."""
    return c + (1.0 - c) / (1.0 + np.exp(-a * (np.asarray(theta) - b)))


def info3pl(theta, a, b, c):
    """Fisher information a² · (Q/P) · ((P − c)/(1 − c))². Peaks slightly above b when c > 0."""
    p = np.clip(p3pl(theta, a, b, c), EPS, 1 - EPS)
    return a**2 * ((1 - p) / p) * ((p - c) / (1 - c)) ** 2


def posterior(items: list[tuple[float, float, float]], responses: list[bool]) -> np.ndarray:
    """Posterior over GRID with the neutral N(0,1) prior, computed in log space."""
    loglik = np.zeros_like(GRID)
    for (a, b, c), u in zip(items, responses):
        p = np.clip(p3pl(GRID, a, b, c), EPS, 1 - EPS)
        loglik += np.log(p) if u else np.log1p(-p)
    logpost = np.log(PRIOR) + loglik
    post = np.exp(logpost - logpost.max())
    return post / post.sum()


def eap(items, responses) -> tuple[float, float]:
    """EAP θ̂ and SE (posterior SD)."""
    post = posterior(items, responses)
    theta = float((GRID * post).sum())
    se = float(math.sqrt(((GRID - theta) ** 2 * post).sum()))
    return theta, se


def prob_above(items, responses, cut: float) -> float:
    """P(θ ≥ cut | data), from the same posterior grid as EAP."""
    post = posterior(items, responses)
    return float(post[GRID >= cut - 1e-12].sum())


def rating(theta: float, se: float) -> tuple[int, int]:
    return round(1000 + 200 * theta), round(1.96 * 200 * se)


def should_stop(n: int, se: float, theta: float, cut: float, *, min_items=10, max_items=20,
                express=False) -> bool:
    if express:
        return n >= 8
    if n >= max_items:
        return True
    if n < min_items:
        return False
    lo, hi = theta - 1.96 * se, theta + 1.96 * se
    return se <= 0.30 or lo >= cut or hi < cut


def item_level(b: float, cuts=(-1.0, 0.0, 1.0)) -> str:
    """Grade band of an item's difficulty; cuts separate intern|junior|middle|senior."""
    grades = ("intern", "junior", "middle", "senior")
    return grades[sum(b >= x for x in cuts)]


# ── validation metrics ─────────────────────────────────────────────────────

def qwk(y_true: list[int], y_pred: list[int], k: int) -> float:
    """Quadratic weighted kappa for ordinal labels 0..k-1."""
    o = np.zeros((k, k))
    for t, p in zip(y_true, y_pred):
        o[t, p] += 1
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    e = np.outer(o.sum(1), o.sum(0)) / o.sum()
    return float(1 - (w * o).sum() / (w * e).sum())


def ndcg_at_k(rels_in_ranked_order: list[float], k: int, all_rels: list[float] | None = None) -> float:
    """nDCG@k with gains 2^rel − 1 and log2(i + 1) discount. IDCG from all_rels if given (recommended)."""
    def dcg(r):
        r = np.asarray(r[:k], dtype=float)
        return float(((2**r - 1) / np.log2(np.arange(2, r.size + 2))).sum())
    ideal = sorted(all_rels if all_rels is not None else rels_in_ranked_order, reverse=True)
    idcg = dcg(ideal)
    return dcg(rels_in_ranked_order) / idcg if idcg > 0 else 0.0


def mrr(rels_in_ranked_order: list[float], threshold: float = 2) -> float:
    for i, r in enumerate(rels_in_ranked_order, 1):
        if r >= threshold:
            return 1.0 / i
    return 0.0


if __name__ == "__main__":
    items = [(1.2, b, 0.25) for b in (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5)]
    for resp in ([True] * 6, [False] * 6, [True, False] * 3):
        t, s = eap(items, resp)
        print(f"{''.join('1' if r else '0' for r in resp)}  θ̂={t:+.3f}  SE={s:.3f}  "
              f"rating={rating(t, s)}  P(θ≥0)={prob_above(items, resp, 0.0):.3f}")
    print("no data: θ̂, SE =", tuple(round(v, 3) for v in eap([], [])))   # ≈ (0, ~1)
    print("info peak (a=1.5,b=0,c=0.25) at θ≈", round(float(GRID[np.argmax(info3pl(GRID, 1.5, 0, 0.25))]), 2))
    print("qwk perfect:", qwk([0, 1, 2, 3], [0, 1, 2, 3], 4), " ndcg:", round(ndcg_at_k([3, 2, 0, 1], 4), 4))
