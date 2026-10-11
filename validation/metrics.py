"""Metric functions for the validation suite (ML-8). Pure; each has a hand-computed golden test.

Ranking metrics follow ARCHITECTURE §2.12: nDCG with gains 2^rel − 1 and log2(i + 1) discounts,
IDCG from *all* relevant items of the pool (not just the returned list); P@k and MRR count
rel >= 2 as relevant; R@k is the share of relevant items found in the top k.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence


def qwk(y_true: Sequence[int], y_pred: Sequence[int], k: int) -> float:
    """Quadratic weighted kappa for ordinal labels 0..k-1 (weights (i − j)² / (k − 1)²)."""
    n = len(y_true)
    if n == 0:
        return float("nan")
    observed = [[0.0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred, strict=True):
        observed[t][p] += 1
    rows = [sum(r) for r in observed]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * observed[i][j]
            den += w * rows[i] * cols[j] / n
    return 1.0 - num / den if den else 1.0


def confusion(y_true: Sequence[int], y_pred: Sequence[int], k: int) -> list[list[int]]:
    m = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred, strict=True):
        m[t][p] += 1
    return m


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")


def dcg(rels: Sequence[float], k: int) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))


def ndcg_at_k(ranked_rels: Sequence[float], all_rels: Sequence[float], k: int) -> float:
    ideal = dcg(sorted(all_rels, reverse=True), k)
    return dcg(ranked_rels, k) / ideal if ideal > 0 else 0.0


def precision_at_k(ranked_rels: Sequence[float], k: int, threshold: float = 2) -> float:
    top = list(ranked_rels[:k])
    return sum(1 for r in top if r >= threshold) / k if k else 0.0


def recall_at_k(ranked_rels: Sequence[float], all_rels: Sequence[float], k: int, threshold: float = 2) -> float:
    relevant = sum(1 for r in all_rels if r >= threshold)
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / relevant if relevant else 0.0


def mrr(ranked_rels: Sequence[float], threshold: float = 2) -> float:
    for i, r in enumerate(ranked_rels, start=1):
        if r >= threshold:
            return 1.0 / i
    return 0.0


def median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100)."""
    s = sorted(values)
    if not s:
        return float("nan")
    rank = max(1, math.ceil(q / 100 * len(s)))
    return float(s[rank - 1])


# ── BM25 baseline ──────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-zа-яё0-9_+#]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


class BM25:
    """Okapi BM25 (k1 = 1.5, b = 0.75) over a fixed corpus of documents."""

    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths) if self.docs else 0.0
        df: Counter[str] = Counter()
        for c in self.docs:
            df.update(c.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: str, i: int) -> float:
        tf, length = self.docs[i], self.lengths[i]
        total = 0.0
        for term in set(tokenize(query)):
            f = tf.get(term, 0)
            if f:
                total += self.idf[term] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
        return total
