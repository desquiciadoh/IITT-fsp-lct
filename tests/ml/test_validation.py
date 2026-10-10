"""ML-8: validation metrics have hand-computed goldens; the pipeline is honest about what it measured."""
from __future__ import annotations

import json
import math
import subprocess

import pytest

from validation import bench_matching as B
from validation import report as R
from validation import sim_assessment as S
from validation.schema import validate_report

# ── assessment metrics ─────────────────────────────────────────────────────

def test_qwk_goldens():
    assert S.quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == pytest.approx(1.0)
    # by hand: O = I/4 except one swap; with y = [0,1,2,3] and p = [1,0,2,3]:
    # sum w·O = 2·(1/9)/4 = 1/18; E = outer(1/4, 1/4) = 1/16 each; sum w = Σ(i−j)²/9 = 40/9,
    # so sum w·E = 40/144 = 5/18 and κ = 1 − (1/18)/(5/18) = 0.8
    assert S.quadratic_weighted_kappa([0, 1, 2, 3], [1, 0, 2, 3]) == pytest.approx(0.8)
    # the confusion matrix of the first report (rows truth, columns result): QWK = 0.763801
    conf = [[793, 738, 33, 0], [391, 2084, 948, 10], [11, 704, 2270, 452], [0, 22, 431, 1113]]
    y = [i for i in range(4) for j in range(4) for _ in range(conf[i][j])]
    p = [j for i in range(4) for j in range(4) for _ in range(conf[i][j])]
    assert S.quadratic_weighted_kappa(y, p) == pytest.approx(0.763801, abs=1e-6)
    with pytest.raises(ValueError):
        S.quadratic_weighted_kappa([], [])


def test_pearson_goldens():
    assert S.pearson_r([1, 2, 3], [2, 4, 7]) == pytest.approx(0.9933992677987828)
    with pytest.raises(ValueError):
        S.pearson_r([1.0], [2.0])


# ── ranking metrics ────────────────────────────────────────────────────────

def test_ndcg_by_hand():
    # ranked [0, 1, 2] vs ideal [2, 1, 0]: DCG = 0 + 1/log2(3) + 3/2; IDCG = 3 + 1/log2(3)
    got = B.ndcg_at_k([0, 1, 2], [2, 1, 0])
    assert got == pytest.approx((1 / math.log2(3) + 1.5) / (3 + 1 / math.log2(3)))
    assert B.ndcg_at_k([0, 0], [0, 0]) == 1.0                     # nothing relevant: perfect by convention
    assert B.ndcg_at_k([3, 2, 1], [1, 2, 3], k=2) == pytest.approx(1.0)


def test_precision_recall_mrr_by_hand():
    rels = [0, 2, 3, 1, 0, 2]
    assert B.precision_at_k(rels, k=10) == pytest.approx(3 / 10)  # divided by k even for short lists
    assert B.recall_at_k(rels, k=3) == pytest.approx(2 / 3)
    assert B.mrr(rels) == pytest.approx(1 / 2)
    assert B.mrr([0, 1]) == 0.0


def test_oracle_reads_only_hidden_truth():
    pos = {"specialization": "backend", "grades": ["middle"], "allow_adjacent": True,
           "must_skills": ["python", "postgresql"], "nice_skills": ["redis"]}
    truth = {"specialization": "backend", "true_grade": "middle", "proficiency": {"python": 0.9, "postgresql": 0.8}}
    # skill = 0.75·0.85 + 0.25·0 = 0.6375; utility = 0.65·0.6375 + 0.35 = 0.764 -> 3
    assert B.relevance(pos, truth) == 3
    assert B.relevance(pos, dict(truth, true_grade="junior")) == 2   # 0.414 + 0.21 = 0.624 -> 2
    assert B.relevance(pos, dict(truth, true_grade="intern")) == 0   # not adjacent
    assert B.relevance(pos, dict(truth, specialization="frontend")) == 0
    assert B.relevance(pos, dict(truth, proficiency={})) == 1         # 0 + 0.35 -> 1


def test_declared_only_ablation_drops_tests_and_fsp():
    from matching.engine.types import CandidateCtx, SkillEvidence
    c = CandidateCtx(public_id="c", specialization="backend", league_grade="middle", league_status="confirmed",
                     theta=1.0, se=0.3, rating=1200, percentile=90.0, strength=88.0,
                     skills=(SkillEvidence("python", "declared", 1.0), SkillEvidence("sql", "test", 1.0)),
                     topic_levels={"sql.joins": "strong"}, fsp_rank="kms", fsp_results=(), salary_min=None,
                     salary_max=None, salary_type=None, work_formats=("remote",), city="", timezone="",
                     last_active_at=None)
    d = B._declared_only(c)
    assert d.skills == (SkillEvidence("python", "declared", 1.0),)    # the test-only skill is gone
    assert (d.fsp_rank, d.league_status, d.strength, d.topic_levels) == (None, "unconfirmed", 50.0, {})


# ── honesty of the report ──────────────────────────────────────────────────

def test_git_sha_has_no_fallback(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        R.git_sha(tmp_path)                                        # not a repository: no made-up SHA
    sha = R.git_sha()
    assert len(sha.split("-")[0]) == 40


def test_targets_table_reports_misses():
    from validation.run import targets
    a = {"generator_errors": 0, "collision_rate": 0.0, "exact_acc": 0.6, "adjacent_acc": 0.99,
         "retest_same_grade": 0.5, "retest_r": 0.7, "median_len": 20.0, "max_family_exposure": 1.0,
         "leak_attack": [{"leak_share": 0.5, "static_dtheta": 0.9, "parametric_dtheta": 0.05}]}
    m = {"non_fsp_parity": 0.9, "pool_p95_ms": 80.0,
         "systems": [{"name": "keyword", "ndcg10": 0.7, "p10": 0.8, "r50": 0.3, "mrr": 0.8},
                     {"name": "ours_no_verified", "ndcg10": 0.6, "p10": 0.7, "r50": 0.3, "mrr": 0.8},
                     {"name": "ours", "ndcg10": 0.65, "p10": 0.75, "r50": 0.3, "mrr": 0.8}]}
    status = {row["metric"]: row["status"] for row in targets(a, m)}
    assert status["exact grade accuracy"] == "MISS" and status["generator errors"] == "PASS"
    assert status["lift over keyword (nDCG@10)"] == "MISS"
    assert status["ablation: verified evidence on - off (nDCG@10)"] == "PASS"
    assert status["leak: parametric |dtheta| at every share"] == "PASS"


@pytest.mark.slow
def test_fast_run_writes_a_valid_report(tmp_path):
    from validation.run import run
    report = run(200, 50, 10, 1, 100, 4, 2026, tmp_path)
    assert validate_report(report) == []
    assert report["synthetic_fixture"] is False and report["git_sha"] != "fixture"
    details = json.loads((tmp_path / "details.json").read_text(encoding="utf-8"))
    assert {row["status"] for row in details["targets"]} <= {"PASS", "MISS"}
    assert details["matching"]["embedding_backend"] in ("local", "hash")
    assert sorted(p.name for p in (tmp_path / "charts").iterdir()) == ["confusion.svg", "leak_attack.svg",
                                                                      "matching.svg", "tif.svg"]
    leak = report["assessment"]["leak_attack"]
    assert [r["leak_share"] for r in leak] == [0.1, 0.3, 0.5]
    assert "+-" not in (tmp_path / "charts" / "leak_attack.svg").read_text(encoding="utf-8")
