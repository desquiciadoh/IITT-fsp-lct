"""Matching benchmark (ML-8, AI-10 part 2; ARCHITECTURE §2.12, targets §5.3). Pure: no Django.

For each of the 60 synthetic positions, every system ranks the SAME candidate set: the position's
specialisation pool after the production hard filters (grade ± adjacent, work format), the set an
employer would see. Ranking quality is judged by a relevance oracle that reads only the hidden
truth (validation/data/truth.jsonl), which no system sees:

    utility = 0.65 · skill + 0.35 · grade,  skill = 0.75 · mean must proficiency + 0.25 · mean nice
    grade = 1 for the true grade in the position's grades, 0.6 for an adjacent one when allowed,
    otherwise relevance 0; relevance 3 / 2 / 1 / 0 at utility ≥ 0.70 / 0.50 / 0.30.

The weights and cut-offs were fixed before any system was scored and were not tuned. (The first
version also scored the candidate's *observable* work formats, which the hard filter uses too;
that term was dropped, and its weight spread proportionally, ML-8 review.)

Systems: keyword (declared skills: 2 per must, 1 per nice), bm25 (CV text vs the job text),
an embedding baseline (USER-bge-m3 when installed, else the lexical hash backend, named
`hashed_ngram`), ours_no_verified (the production scorer on declared information only: declared
skills, no tests, no FSP, every grade unconfirmed, neutral strength), and ours (the production
scorer with the position's preset and EMBEDDINGS off, the production default).

Metrics: nDCG@10 (gains 2^rel − 1, ideal ranking of the same pool), P@10 (relevance ≥ 2, divided
by 10), R@50 (relevant in the top 50 / relevant in the pool), MRR (first relevance ≥ 2);
non-FSP parity = top-10 exposure rate of relevant non-FSP candidates / that of relevant FSP
candidates (unclipped); scoring latency p95 over positions (filter + score_pool).
"""
from __future__ import annotations

import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from matching.engine.embeddings import EmbeddingUnavailable, active_model_id, embed_batch
from matching.engine.features import cosine
from matching.engine.score import passes_hard_filters, preset, score_pool
from matching.engine.types import CandidateCtx, NeedCtx, SkillEvidence

from validation.synth import AS_OF, to_candidate_ctx

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "seed_data" / "full"
TRUTH_PATH = ROOT / "validation" / "data" / "truth.jsonl"
NOW = AS_OF


def tokenize(text: str) -> list[str]:
    import re
    return re.findall(r"\w+", text.lower())


# ── ranking metrics ────────────────────────────────────────────────────────

def dcg_at_k(rels, k: int = 10) -> float:
    return sum((2.0 ** r - 1.0) / math.log2(i + 2.0) for i, r in enumerate(rels[:k]))


def ndcg_at_k(ranked_rels, pool_rels, k: int = 10) -> float:
    """nDCG of a ranking against the ideal ordering of the same pool (1.0 if nothing is relevant)."""
    ideal = dcg_at_k(sorted(pool_rels, reverse=True), k)
    return dcg_at_k(ranked_rels, k) / ideal if ideal > 0 else 1.0


def precision_at_k(ranked_rels, k: int = 10, threshold: int = 2) -> float:
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / k


def recall_at_k(ranked_rels, k: int = 50, threshold: int = 2) -> float:
    total = sum(1 for r in ranked_rels if r >= threshold)
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / total if total else 1.0


def mrr(ranked_rels, threshold: int = 2) -> float:
    return next((1.0 / (i + 1) for i, r in enumerate(ranked_rels) if r >= threshold), 0.0)


# ── the oracle ─────────────────────────────────────────────────────────────

GRADES = ("intern", "junior", "middle", "senior")


def relevance(pos: dict, truth: dict) -> int:
    """0..3 from the hidden truth only (proficiency and true grade)."""
    if truth["specialization"] != pos["specialization"]:
        return 0
    g = GRADES.index(truth["true_grade"])
    if truth["true_grade"] in pos["grades"]:
        grade = 1.0
    elif pos.get("allow_adjacent") and any(abs(g - GRADES.index(x)) == 1 for x in pos["grades"]):
        grade = 0.6
    else:
        return 0
    prof = truth["proficiency"]
    must = [prof.get(s, 0.0) for s in pos["must_skills"]]
    nice = [prof.get(s, 0.0) for s in pos["nice_skills"]]
    skill = 0.75 * (statistics.fmean(must) if must else 1.0) + 0.25 * (statistics.fmean(nice) if nice else 1.0)
    utility = 0.65 * skill + 0.35 * grade
    return 3 if utility >= 0.70 else 2 if utility >= 0.50 else 1 if utility >= 0.30 else 0


# ── BM25 ───────────────────────────────────────────────────────────────────

class BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = statistics.fmean(len(d) for d in docs.values()) if docs else 1.0
        df: Counter = Counter()
        for d in docs.values():
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log((n - f + 0.5) / (f + 0.5) + 1.0) for t, f in df.items()}
        self.tf = {k: Counter(d) for k, d in docs.items()}

    def score(self, query: list[str], doc_id: str) -> float:
        tf, dl = self.tf[doc_id], len(self.docs[doc_id])
        return sum(self.idf.get(q, 0.0) * tf[q] * (self.k1 + 1) / (tf[q] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                   for q in query if q in tf)


# ── systems ────────────────────────────────────────────────────────────────

def _declared_only(c: CandidateCtx) -> CandidateCtx:
    """What the scorer would know without tests or FSP: declared skills at the production level
    (1.0, the declared source factor applies in the scorer), unconfirmed grade, neutral strength."""
    import dataclasses
    return dataclasses.replace(c, skills=tuple(SkillEvidence(s.skill_id, "declared", 1.0) for s in c.skills
                                               if s.source == "declared"),
                               fsp_results=(), fsp_rank=None, league_status="unconfirmed", strength=50.0,
                               percentile=50.0, topic_levels={}, microtask_dates=())


def _ranked(scores: dict[str, float]) -> list[str]:
    return [pid for pid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def _load(seed_dir: Path, truth_path: Path):
    def rows(path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    cands = rows(seed_dir / "candidates.jsonl")
    leagues = {r["public_id"]: r for r in rows(seed_dir / "leagues.jsonl")}
    fsp = {r["public_id"]: r for r in rows(seed_dir / "fsp_registry.jsonl")}
    positions = rows(seed_dir / "positions.jsonl")
    truth = {r["public_id"]: r for r in rows(truth_path)}
    return cands, leagues, fsp, positions, truth


def run_matching_benchmark(n_positions: int = 60, seed_dir: Path = SEED_DIR,
                           truth_path: Path = TRUTH_PATH) -> dict[str, Any]:
    cands, leagues, fsp, positions, truth = _load(seed_dir, truth_path)
    positions = positions[:n_positions]
    ctx = {c["public_id"]: to_candidate_ctx(c, leagues.get(c["public_id"]), fsp.get(c["public_id"])) for c in cands}
    declared = {pid: _declared_only(c) for pid, c in ctx.items()}
    has_fsp = {pid: bool(c.fsp_results or c.fsp_rank) for pid, c in ctx.items()}
    rows = {c["public_id"]: c for c in cands}

    # embedding baseline: the real model when installed, else the labelled lexical hash backend
    texts = [c.get("cv_text", "") for c in cands]
    try:
        kind, name = "local", "embeddings_only"
        vectors = embed_batch(texts, kind)
    except EmbeddingUnavailable:
        kind, name = "hash", "hashed_ngram"
        vectors = embed_batch(texts, kind)
    vec = dict(zip((c["public_id"] for c in cands), vectors, strict=True))
    bm25 = BM25({c["public_id"]: tokenize(c.get("cv_text", "")) for c in cands})

    systems = ("keyword", "bm25", name, "ours_no_verified", "ours")
    scores: dict[str, dict[str, list[float]]] = {s: {"ndcg10": [], "p10": [], "r50": [], "mrr": []} for s in systems}
    latencies, pool_sizes, relevant_counts, filtered_out_relevant = [], [], [], []
    exposure = {"fsp": [0, 0], "non_fsp": [0, 0]}                  # [top-10 appearances, eligible]
    for pos in positions:
        need = NeedCtx(position_id=pos["position_id"], specialization=pos["specialization"],
                       grades=tuple(pos["grades"]), allow_adjacent=pos.get("allow_adjacent", False),
                       must_skills=tuple(pos["must_skills"]), nice_skills=tuple(pos["nice_skills"]),
                       work_formats=tuple(pos["work_formats"]), location=pos.get("location", ""),
                       salary_min=pos["salary_min"], salary_max=pos["salary_max"], salary_type=pos["salary_type"])
        spec_ids = sorted(pid for pid, c in ctx.items() if c.specialization == need.specialization)
        t0 = time.perf_counter()
        pool = [pid for pid in spec_ids if passes_hard_filters(need, ctx[pid])]
        ours = [s.public_id for s in score_pool(need, [ctx[p] for p in pool], preset(pos.get("preset", "balanced")), NOW)]
        latencies.append((time.perf_counter() - t0) * 1000)
        rel = {pid: relevance(pos, truth[pid]) for pid in spec_ids}
        pool_sizes.append(len(pool))
        relevant_counts.append(sum(1 for p in pool if rel[p] >= 2))
        filtered_out_relevant.append(sum(1 for p in spec_ids if rel[p] >= 2 and p not in set(pool)))

        must, nice = set(need.must_skills), set(need.nice_skills)
        query = tokenize(pos.get("description", ""))
        q_vec = embed_batch([pos.get("description", "")], kind)[0]
        ranked = {
            "keyword": _ranked({p: 2 * len(must & {s["skill_id"] for s in rows[p]["skills"] if s["source"] == "declared"})
                                + len(nice & {s["skill_id"] for s in rows[p]["skills"] if s["source"] == "declared"})
                                for p in pool}),
            "bm25": _ranked({p: bm25.score(query, p) for p in pool}),
            name: _ranked({p: cosine(q_vec, vec[p]) if q_vec and vec[p] else 0.0 for p in pool}),
            "ours_no_verified": [s.public_id for s in score_pool(need, [declared[p] for p in pool],
                                                                 preset(pos.get("preset", "balanced")), NOW)],
            "ours": ours,
        }
        pool_rels = [rel[p] for p in pool]
        for system, order in ranked.items():
            rels = [rel[p] for p in order]
            scores[system]["ndcg10"].append(ndcg_at_k(rels, pool_rels))
            scores[system]["p10"].append(precision_at_k(rels))
            scores[system]["r50"].append(recall_at_k(rels))
            scores[system]["mrr"].append(mrr(rels))
        top = set(ours[:10])
        for p in pool:
            if rel[p] >= 2:
                group = exposure["fsp" if has_fsp[p] else "non_fsp"]
                group[0] += p in top
                group[1] += 1

    rate = {g: (a / b if b else 0.0) for g, (a, b) in exposure.items()}
    return {
        "candidates": len(cands), "needs": len(positions),
        "non_fsp_parity": round(rate["non_fsp"] / rate["fsp"], 4) if rate["fsp"] else 0.0,
        "pool_p95_ms": round(float(np.percentile(latencies, 95)), 2),
        "systems": [{"name": s, **{k: round(statistics.fmean(v), 4) for k, v in scores[s].items()}} for s in systems],
        "_details": {
            "embedding_backend": kind, "embedding_model": active_model_id(kind),
            "pool_size_median": statistics.median(pool_sizes),
            "relevant_in_pool_median": statistics.median(relevant_counts),
            "relevant_share_in_pool": sum(relevant_counts) / sum(pool_sizes) if sum(pool_sizes) else 0.0,
            "relevant_removed_by_hard_filter_share": (sum(filtered_out_relevant)
                                                      / max(1, sum(filtered_out_relevant) + sum(relevant_counts))),
            "top10_exposure_rate_relevant": rate, "latency_ms_median": statistics.median(latencies),
        },
    }
