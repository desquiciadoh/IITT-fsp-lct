"""Matching benchmark suite (ML-8, AI-10 part 2; ARCHITECTURE §2.12).

Benchmarks 5 candidate ranking systems against an objective hidden-truth relevance oracle (0-3):
  1. keyword: keyword overlap on declared skills;
  2. bm25: BM25 text retrieval on candidate CV text;
  3. embeddings_only: cosine similarity between position and profile embeddings;
  4. ours_no_verified: production matching engine without verified test/FSP evidence;
  5. ours: full production matching engine with verified CAT skills, FSP boost, Profile Strength.

Evaluates:
  - nDCG@10, Precision@10 (relevance >= 2), Recall@50, and MRR per system;
  - Non-FSP exposure parity in top-10 recommendations;
  - Scoring latency p95 (ms).

Pure: no Django.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import numpy as np

from assessment.families.base import GRADES
from matching.engine.embeddings import candidate_embedding_text, embed_text
from matching.engine.score import passes_hard_filters, score_pool
from matching.engine.types import CandidateCtx, NeedCtx, SkillEvidence, Weights
from validation.synth import AS_OF, to_candidate_ctx

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "seed_data" / "full"
TRUTH_PATH = ROOT / "validation" / "data" / "truth.jsonl"
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def cosine_similarity(u: Sequence[float] | None, v: Sequence[float] | None) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(a * b for a, b in zip(u, v))
    norm_u = math.sqrt(sum(a * a for a in u))
    norm_v = math.sqrt(sum(b * b for b in v))
    if norm_u == 0.0 or norm_v == 0.0:
        return 0.0
    return float(dot / (norm_u * norm_v))


def dcg_at_k(rels: Sequence[int], k: int = 10) -> float:
    return sum((2.0 ** r - 1.0) / math.log2(i + 2.0) for i, r in enumerate(rels[:k]))


def ndcg_at_k(ranked_rels: Sequence[int], ideal_rels: Sequence[int], k: int = 10) -> float:
    idcg = dcg_at_k(sorted(ideal_rels, reverse=True), k)
    if idcg <= 0.0:
        return 1.0
    return float(np.clip(dcg_at_k(ranked_rels, k) / idcg, 0.0, 1.0))


def compute_relevance(pos: dict, truth: dict, cand_row: dict) -> int:
    """Hidden-truth relevance oracle (0-3):

    Uses candidate's true latent skills and actual grade from truth.jsonl,
    which the platform's ranking algorithms never see during scoring.
    """
    if truth.get("specialization") != pos.get("specialization"):
        return 0

    true_grade = truth.get("true_grade", "")
    target_grades = pos.get("grades", [])
    allow_adjacent = pos.get("allow_adjacent", False)

    # Grade match check
    if true_grade in target_grades:
        grade_score = 1.0
    elif allow_adjacent and any(abs(GRADES.index(true_grade) - GRADES.index(g)) == 1 for g in target_grades):
        grade_score = 0.6
    else:
        return 0  # Hard grade mismatch

    # Latent proficiency from ground truth
    prof = truth.get("proficiency", {})
    must_skills = pos.get("must_skills", [])
    nice_skills = pos.get("nice_skills", [])

    must_prof = [prof.get(s, 0.0) for s in must_skills]
    nice_prof = [prof.get(s, 0.0) for s in nice_skills]

    must_score = sum(must_prof) / len(must_prof) if must_prof else 1.0
    nice_score = sum(nice_prof) / len(nice_prof) if nice_prof else 1.0
    skill_score = 0.75 * must_score + 0.25 * nice_score

    # Work format compatibility
    pos_fmts = set(pos.get("work_formats", []))
    cand_fmts = set(cand_row.get("work_formats", []))
    fmt_score = 1.0 if (pos_fmts & cand_fmts) else 0.5

    # Overall continuous utility
    utility = 0.55 * skill_score + 0.30 * grade_score + 0.15 * fmt_score

    if utility >= 0.70:
        return 3
    if utility >= 0.50:
        return 2
    if utility >= 0.30:
        return 1
    return 0


class BM25Model:
    """Standard in-memory BM25 index over candidate CV texts."""

    def __init__(self, corpus_by_id: dict[str, list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.corpus = corpus_by_id
        self.n_docs = len(corpus_by_id)
        total_tokens = sum(len(doc) for doc in corpus_by_id.values())
        self.avgdl = (total_tokens / self.n_docs) if self.n_docs > 0 else 1.0

        df: Counter[str] = Counter()
        for doc in corpus_by_id.values():
            for term in set(doc):
                df[term] += 1

        self.idf = {
            t: math.log((self.n_docs - freq + 0.5) / (freq + 0.5) + 1.0)
            for t, freq in df.items()
        }

    def score(self, query_tokens: list[str], doc_id: str) -> float:
        doc = self.corpus.get(doc_id, [])
        if not doc:
            return 0.0
        dl = len(doc)
        term_counts = Counter(doc)
        score = 0.0
        for q in query_tokens:
            if q in term_counts:
                f = term_counts[q]
                num = f * (self.k1 + 1.0)
                den = f + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                score += self.idf.get(q, 0.0) * (num / den)
        return score


def run_matching_benchmark(
    n_positions: int = 60,
    seed: int = 2026,
    seed_dir: Path = SEED_DIR,
    truth_path: Path = TRUTH_PATH,
) -> dict[str, Any]:
    """Execute full matching benchmark across 5 systems."""
    # Force local embeddings for deterministic testing
    os.environ["EMBEDDINGS"] = "local"

    cands_raw = [json.loads(line) for line in (seed_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
    leagues_raw = {lg["public_id"]: lg for lg in (json.loads(line) for line in (seed_dir / "leagues.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    fsp_raw = {f["public_id"]: f for f in (json.loads(line) for line in (seed_dir / "fsp_registry.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    positions_raw = [json.loads(line) for line in (seed_dir / "positions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    truth_raw = {t["public_id"]: t for t in (json.loads(line) for line in truth_path.read_text(encoding="utf-8").splitlines() if line)}

    cand_by_id = {c["public_id"]: c for c in cands_raw}
    positions = positions_raw[:n_positions]

    # Convert candidates to CandidateCtx
    ctxs = [to_candidate_ctx(c, leagues_raw.get(c["public_id"]), fsp_raw.get(c["public_id"])) for c in cands_raw]
    ctx_by_id = {c.public_id: c for c in ctxs}

    # Pre-embed candidate profiles
    c_texts = [
        candidate_embedding_text(
            about=c.get("cv_text", ""),
            skills=[s["skill_id"] for s in c.get("skills", [])],
        )
        for c in cands_raw
    ]
    cand_embeds = {c["public_id"]: embed_text(txt) for c, txt in zip(cands_raw, c_texts)}

    # Attach embeddings to context DTOs
    ctx_with_embeds = {
        c.public_id: CandidateCtx(**{**c.__dict__, "embedding": cand_embeds.get(c.public_id)})
        for c in ctxs
    }

    # Pre-build BM25 index over candidate CV texts
    bm25_corpus = {c["public_id"]: tokenize(c.get("cv_text", "")) for c in cands_raw}
    bm25_model = BM25Model(bm25_corpus)

    # Metric accumulators per system
    system_names = ("keyword", "bm25", "embeddings_only", "ours_no_verified", "ours")
    metrics: dict[str, dict[str, list[float]]] = {
        s: {"ndcg10": [], "p10": [], "r50": [], "mrr": []} for s in system_names
    }

    # Exposure trackers for non-FSP parity
    top10_fsp_count = 0
    top10_non_fsp_count = 0
    total_fsp_candidates = sum(bool(c.fsp_results or c.fsp_rank) for c in ctxs)
    total_non_fsp_candidates = len(ctxs) - total_fsp_candidates

    pool_latencies_ms: list[float] = []

    for pos in positions:
        spec = pos["specialization"]
        spec_cands = [c for c in cands_raw if c["specialization"] == spec]
        spec_cand_ids = [c["public_id"] for c in spec_cands]

        # Ground truth relevance map for this position
        rel_map = {
            pid: compute_relevance(pos, truth_raw.get(pid, {}), cand_by_id[pid])
            for pid in spec_cand_ids
        }
        all_rels = list(rel_map.values())
        tot_relevant = sum(r >= 2 for r in all_rels)

        # 1. System: keyword overlap on declared skills
        must_skills = set(pos.get("must_skills", []))
        nice_skills = set(pos.get("nice_skills", []))
        kw_scores = []
        for c in spec_cands:
            decl = {s["skill_id"] for s in c.get("skills", []) if s.get("source") == "declared"}
            score = 2.0 * len(decl & must_skills) + 1.0 * len(decl & nice_skills)
            kw_scores.append((score, c["public_id"]))
        kw_ranked = [pid for _, pid in sorted(kw_scores, key=lambda x: (-x[0], x[1]))]

        # 2. System: BM25 text retrieval
        pos_query = tokenize(pos.get("description", ""))
        bm_scores = [(bm25_model.score(pos_query, pid), pid) for pid in spec_cand_ids]
        bm_ranked = [pid for _, pid in sorted(bm_scores, key=lambda x: (-x[0], x[1]))]

        # 3. System: embeddings_only (cosine similarity)
        pos_emb = embed_text(pos.get("description", ""))
        emb_scores = [(cosine_similarity(pos_emb, cand_embeds.get(pid)), pid) for pid in spec_cand_ids]
        emb_ranked = [pid for _, pid in sorted(emb_scores, key=lambda x: (-x[0], x[1]))]

        # 4 & 5. Production Matcher systems
        need = NeedCtx(
            position_id=pos["position_id"],
            specialization=spec,
            grades=tuple(pos["grades"]),
            allow_adjacent=pos.get("allow_adjacent", False),
            must_skills=tuple(pos.get("must_skills", [])),
            nice_skills=tuple(pos.get("nice_skills", [])),
            work_formats=tuple(pos.get("work_formats", [])),
            location=pos.get("location", ""),
            salary_min=pos["salary_min"],
            salary_max=pos["salary_max"],
            salary_type=pos["salary_type"],
            embedding=pos_emb,
        )

        # Hard-filtered candidate pool
        filtered_cands = [
            ctx_with_embeds[pid]
            for pid in spec_cand_ids
            if passes_hard_filters(need, ctx_with_embeds[pid])
        ]

        # System 4: ours_no_verified (all evidence stripped to declared)
        no_ver_cands = []
        for c in filtered_cands:
            stripped_skills = tuple(SkillEvidence(s.skill_id, "declared", 0.4) for s in c.skills)
            no_ver_cands.append(
                CandidateCtx(
                    **{
                        **c.__dict__,
                        "skills": stripped_skills,
                        "fsp_results": (),
                        "fsp_rank": None,
                        "league_status": "unconfirmed",
                        "strength": 50.0,
                    }
                )
            )
        ours_nv_scored = score_pool(need, no_ver_cands, Weights(), AS_OF)
        ours_nv_ranked = [s.public_id for s in ours_nv_scored]

        # System 5: ours (full production matcher)
        t0 = time.time()
        ours_scored = score_pool(need, filtered_cands, Weights(), AS_OF)
        dt_ms = (time.time() - t0) * 1000.0
        pool_latencies_ms.append(dt_ms)
        ours_ranked = [s.public_id for s in ours_scored]

        # Non-FSP exposure tracking in top 10 of full production matcher
        for s in ours_scored[:10]:
            cand_obj = ctx_by_id[s.public_id]
            if cand_obj.fsp_results or cand_obj.fsp_rank:
                top10_fsp_count += 1
            else:
                top10_non_fsp_count += 1

        # Calculate metrics for each system
        ranked_systems = (
            ("keyword", kw_ranked),
            ("bm25", bm_ranked),
            ("embeddings_only", emb_ranked),
            ("ours_no_verified", ours_nv_ranked),
            ("ours", ours_ranked),
        )

        for s_name, r_ids in ranked_systems:
            rels = [rel_map.get(pid, 0) for pid in r_ids]
            ndcg = ndcg_at_k(rels, all_rels, k=10)
            p10 = sum(r >= 2 for r in rels[:10]) / 10.0 if len(rels) >= 10 else (sum(r >= 2 for r in rels) / max(1, len(rels)))
            r50 = (sum(r >= 2 for r in rels[:50]) / tot_relevant) if tot_relevant > 0 else 1.0

            mrr = 0.0
            for idx, r in enumerate(rels):
                if r >= 2:
                    mrr = 1.0 / (idx + 1)
                    break

            metrics[s_name]["ndcg10"].append(ndcg)
            metrics[s_name]["p10"].append(p10)
            metrics[s_name]["r50"].append(r50)
            metrics[s_name]["mrr"].append(mrr)

    # Aggregate metrics across all positions
    systems_summary = []
    for s_name in system_names:
        systems_summary.append({
            "name": s_name,
            "ndcg10": round(float(np.mean(metrics[s_name]["ndcg10"])), 4),
            "p10": round(float(np.mean(metrics[s_name]["p10"])), 4),
            "r50": round(float(np.mean(metrics[s_name]["r50"])), 4),
            "mrr": round(float(np.mean(metrics[s_name]["mrr"])), 4),
        })

    # Non-FSP exposure parity
    exp_fsp = (top10_fsp_count / total_fsp_candidates) if total_fsp_candidates > 0 else 1.0
    exp_non_fsp = (top10_non_fsp_count / total_non_fsp_candidates) if total_non_fsp_candidates > 0 else 1.0
    non_fsp_parity = float(np.clip(exp_non_fsp / exp_fsp, 0.0, 1.0)) if exp_fsp > 0 else 1.0

    p95_latency = float(np.percentile(pool_latencies_ms, 95)) if pool_latencies_ms else 0.0

    return {
        "candidates": len(cands_raw),
        "needs": len(positions),
        "non_fsp_parity": round(non_fsp_parity, 4),
        "pool_p95_ms": round(p95_latency, 2),
        "systems": systems_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run matching system benchmarks against hidden-truth oracle.")
    parser.add_argument("--positions", type=int, default=60, help="Number of positions to evaluate (default: 60)")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed (default: 2026)")
    parser.add_argument("--out", type=str, default="", help="Optional JSON file to save benchmark metrics")
    args = parser.parse_args(argv)

    print(f"Running matching benchmark on {args.positions} positions...")
    res = run_matching_benchmark(n_positions=args.positions, seed=args.seed)
    output_str = json.dumps(res, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output_str + "\n", encoding="utf-8")
        print(f"Wrote benchmark results to {args.out}")
    else:
        sys.stdout.write(output_str + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
