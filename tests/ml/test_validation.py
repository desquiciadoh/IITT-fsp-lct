"""Unit tests for ML-8 validation suite (sim_assessment, bench_matching, report). Pure: no Django."""
from __future__ import annotations

import math
import numpy as np
import pytest

from validation.schema import validate_report


def test_quadratic_weighted_kappa_properties():
    from validation.sim_assessment import quadratic_weighted_kappa

    # Perfect agreement
    y_true = [0, 1, 2, 3, 1, 2, 0, 3]
    y_pred = [0, 1, 2, 3, 1, 2, 0, 3]
    assert math.isclose(quadratic_weighted_kappa(y_true, y_pred, 4), 1.0, abs_tol=1e-5)

    # Disagreement by at most 1 grade still yields high kappa
    y_near = [0, 1, 2, 2, 1, 2, 1, 3]
    k_near = quadratic_weighted_kappa(y_true, y_near, 4)
    assert 0.7 <= k_near <= 1.0

    # Complete reversal gives negative kappa
    y_rev = [3, 2, 1, 0, 2, 1, 3, 0]
    k_rev = quadratic_weighted_kappa(y_true, y_rev, 4)
    assert k_rev < 0.0


def test_pearson_r_properties():
    from validation.sim_assessment import pearson_r

    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert math.isclose(pearson_r(x, x), 1.0, abs_tol=1e-5)
    assert math.isclose(pearson_r(x, [-v for v in x]), -1.0, abs_tol=1e-5)
    assert math.isclose(pearson_r([1.0, 1.0], [2.0, 3.0]), 0.0, abs_tol=1e-5)


def test_dcg_and_ndcg_properties():
    from validation.bench_matching import dcg_at_k, ndcg_at_k

    # Ideal ranking has nDCG = 1.0
    rels = [3, 3, 2, 2, 1, 0, 0]
    assert math.isclose(ndcg_at_k(rels, rels, k=10), 1.0, abs_tol=1e-5)

    # Suboptimal ranking has nDCG < 1.0
    sub_rels = [0, 1, 2, 2, 3, 3, 0]
    val = ndcg_at_k(sub_rels, rels, k=10)
    assert 0.0 < val < 1.0


def test_relevance_oracle():
    from validation.bench_matching import compute_relevance

    pos = {
        "specialization": "backend",
        "grades": ["middle"],
        "allow_adjacent": True,
        "must_skills": ["python", "postgresql"],
        "nice_skills": ["redis"],
        "work_formats": ["remote", "hybrid"],
    }

    # Wrong specialization -> 0
    t_wrong_spec = {"specialization": "frontend", "true_grade": "middle", "proficiency": {"python": 0.9}}
    c_dummy = {"work_formats": ["remote"]}
    assert compute_relevance(pos, t_wrong_spec, c_dummy) == 0

    # Wrong non-adjacent grade -> 0
    t_wrong_grade = {"specialization": "backend", "true_grade": "intern", "proficiency": {"python": 0.9}}
    assert compute_relevance(pos, t_wrong_grade, c_dummy) == 0

    # High match: middle backend with high proficiencies
    t_strong = {
        "specialization": "backend",
        "true_grade": "middle",
        "proficiency": {"python": 0.95, "postgresql": 0.90, "redis": 0.85},
    }
    assert compute_relevance(pos, t_strong, c_dummy) == 3

    # Marginal match: junior with low proficiency
    t_weak = {
        "specialization": "backend",
        "true_grade": "junior",
        "proficiency": {"python": 0.35, "postgresql": 0.20},
    }
    assert compute_relevance(pos, t_weak, c_dummy) in (0, 1)


def test_sim_assessment_quick_run():
    from validation.sim_assessment import run_assessment_simulation

    # Fast test run with n=60
    res = run_assessment_simulation(n_simulees=60, seed=2026, retest_n=30, leak_n=30)
    assert res["simulees"] == 60
    assert 0.0 <= res["exact_acc"] <= 1.0
    assert 0.0 <= res["adjacent_acc"] <= 1.0
    assert -1.0 <= res["qwk"] <= 1.0
    assert -1.0 <= res["retest_r"] <= 1.0
    assert len(res["confusion"]) == 4
    assert all(len(row) == 4 for row in res["confusion"])
    assert sum(sum(r) for r in res["confusion"]) == 60
    assert len(res["leak_attack"]) == 3
    for row in res["leak_attack"]:
        assert row["static_dtheta"] >= row["parametric_dtheta"] - 0.05


def test_bench_matching_quick_run():
    from validation.bench_matching import run_matching_benchmark

    res = run_matching_benchmark(n_positions=5, seed=2026)
    assert res["candidates"] > 0
    assert res["needs"] == 5
    assert len(res["systems"]) == 5
    system_names = [s["name"] for s in res["systems"]]
    assert system_names == ["keyword", "bm25", "embeddings_only", "ours_no_verified", "ours"]
    # Our full system should have high nDCG and P10
    ours = next(s for s in res["systems"] if s["name"] == "ours")
    assert ours["ndcg10"] > 0.4
    assert ours["p10"] > 0.5


def test_full_report_generation_and_schema_validation(tmp_path):
    from validation.report import build_validation_report

    assessment_data = {
        "simulees": 100,
        "exact_acc": 0.65,
        "adjacent_acc": 0.98,
        "qwk": 0.72,
        "retest_same_grade": 0.85,
        "retest_r": 0.91,
        "median_len": 14.0,
        "max_family_exposure": 0.35,
        "collision_rate": 0.0,
        "generator_errors": 0,
        "confusion": [[20, 5, 0, 0], [3, 22, 5, 0], [0, 4, 21, 5], [0, 0, 3, 12]],
        "tif": {"theta": [-2.0, -1.0, 0.0, 1.0, 2.0], "info": [1.5, 3.2, 4.0, 3.1, 1.8]},
        "leak_attack": [
            {"leak_share": 0.1, "static_dtheta": 0.25, "parametric_dtheta": -0.05},
            {"leak_share": 0.3, "static_dtheta": 0.55, "parametric_dtheta": -0.15},
            {"leak_share": 0.5, "static_dtheta": 0.88, "parametric_dtheta": -0.22},
        ],
    }

    matching_data = {
        "candidates": 1500,
        "needs": 60,
        "non_fsp_parity": 0.88,
        "pool_p95_ms": 120.0,
        "systems": [
            {"name": "keyword", "ndcg10": 0.55, "p10": 0.58, "r50": 0.18, "mrr": 0.65},
            {"name": "bm25", "ndcg10": 0.45, "p10": 0.52, "r50": 0.15, "mrr": 0.75},
            {"name": "embeddings_only", "ndcg10": 0.40, "p10": 0.48, "r50": 0.12, "mrr": 0.80},
            {"name": "ours_no_verified", "ndcg10": 0.56, "p10": 0.76, "r50": 0.20, "mrr": 0.86},
            {"name": "ours", "ndcg10": 0.65, "p10": 0.84, "r50": 0.23, "mrr": 0.98},
        ],
    }

    report = build_validation_report(assessment_data, matching_data)
    assert report["synthetic_fixture"] is False
    assert report["git_sha"] != "fixture"
    errs = validate_report(report)
    assert errs == []


def test_chart_generation(tmp_path):
    from validation.charts import generate_all_charts

    report_data = {
        "assessment": {
            "confusion": [[20, 5, 0, 0], [3, 22, 5, 0], [0, 4, 21, 5], [0, 0, 3, 12]],
            "tif": {"theta": [-2.0, -1.0, 0.0, 1.0, 2.0], "info": [1.5, 3.2, 4.0, 3.1, 1.8]},
            "leak_attack": [
                {"leak_share": 0.1, "static_dtheta": 0.25, "parametric_dtheta": -0.05},
                {"leak_share": 0.3, "static_dtheta": 0.55, "parametric_dtheta": -0.15},
                {"leak_share": 0.5, "static_dtheta": 0.88, "parametric_dtheta": -0.22},
            ],
        },
        "matching": {
            "systems": [
                {"name": "keyword", "ndcg10": 0.55, "p10": 0.58, "r50": 0.18, "mrr": 0.65},
                {"name": "ours", "ndcg10": 0.65, "p10": 0.84, "r50": 0.23, "mrr": 0.98},
            ]
        },
    }

    charts_dir = tmp_path / "charts"
    paths = generate_all_charts(report_data, charts_dir)
    assert len(paths) == 4
    for p in paths:
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "<svg" in text
        assert "</svg>" in text
