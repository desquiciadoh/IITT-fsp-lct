"""Tests for ML-11 (Leak and drift monitor + IRT recalibration).

Pure tests: no DB, no network, runs under pytest tests/ml.
"""
from __future__ import annotations

import random
import pytest
from assessment.engine import monitor as M
from assessment.engine.irt import p_3pl
from assessment.families.base import FamilyMeta


def _meta(fid="be.test.item.v1", a=1.2, b=0.0, c=0.25) -> FamilyMeta:
    return FamilyMeta(
        id=fid,
        version=1,
        specs=("backend",),
        topic="backend.http",
        skills=("python",),
        format="concept_mcq",
        a=a,
        b=b,
        c=c,
        time_limit_s=60,
    )


def _simulate_responses(
    meta: FamilyMeta,
    n_per_band: int = 25,
    seed: int = 42,
    leak: bool = False,
    drift: bool = False,
) -> list[M.ItemResponse]:
    rng = random.Random(seed)
    resps = []

    for _, th_lo, th_hi in M.BAND_CUTS:
        for _ in range(n_per_band):
            th = rng.uniform(th_lo, th_hi)
            prob = p_3pl(th, meta.a, meta.b, meta.c)

            if leak and th < 0.0:
                # In leak scenario: weak candidates get high accuracy
                prob = 0.95
            elif drift and th > 0.0:
                # In drift scenario: strong candidates fail unexpectedly
                prob = 0.15

            correct = rng.random() < prob
            resps.append(M.ItemResponse(family_id=meta.id, theta=th, correct=correct))

    return resps


def test_normal_family_stays_active():
    meta = _meta(a=1.3, b=0.0, c=0.25)
    resps = _simulate_responses(meta, n_per_band=30, seed=123)
    rep = M.analyze_family(meta, resps)

    assert rep.status == "active"
    assert rep.flags == []
    assert rep.exposures == 120
    assert abs(rep.observed_rate - rep.expected_rate) < 0.15
    assert rep.calibrated_a is not None and rep.calibrated_a >= 0.6


def test_leaked_family_is_flagged():
    meta = _meta(a=1.4, b=0.5, c=0.25)
    resps = _simulate_responses(meta, n_per_band=30, seed=999, leak=True)
    rep = M.analyze_family(meta, resps)

    assert rep.status == "flagged"
    assert "leak_suspected" in rep.flags
    # Weak bands have large positive z-scores
    intern_stat = next(bs for bs in rep.bands if bs.band == "intern")
    assert intern_stat.z_score >= 2.0


def test_content_drift_is_flagged():
    meta = _meta(a=1.3, b=-0.5, c=0.25)
    resps = _simulate_responses(meta, n_per_band=30, seed=777, drift=True)
    rep = M.analyze_family(meta, resps)

    assert rep.status == "flagged"
    assert "content_drift" in rep.flags
    senior_stat = next(bs for bs in rep.bands if bs.band == "senior")
    assert senior_stat.z_score <= -2.0


def test_low_discrimination_is_retired():
    # Item authored with a < 0.6 must be retired
    meta_weak = _meta(fid="be.weak.item.v1", a=0.45, b=0.0, c=0.25)
    resps = _simulate_responses(meta_weak, n_per_band=20, seed=11)
    rep = M.analyze_family(meta_weak, resps)

    assert rep.status == "retired"
    assert "low_discrimination" in rep.flags


def test_recalibration_recovers_parameters():
    meta = _meta(a=1.5, b=0.4, c=0.25)
    resps = _simulate_responses(meta, n_per_band=40, seed=42)
    rep = M.analyze_family(meta, resps)

    assert rep.calibrated_a == pytest.approx(1.5, abs=0.5)
    assert rep.calibrated_b == pytest.approx(0.4, abs=0.5)


def test_monitor_families_pool_and_json_serialization():
    m_active = _meta("be.item.active.v1", a=1.2, b=0.0)
    m_leaked = _meta("be.item.leaked.v1", a=1.3, b=0.2)
    m_weak = _meta("be.item.weak.v1", a=0.4, b=0.0)

    resps = (
        _simulate_responses(m_active, n_per_band=20, seed=1)
        + _simulate_responses(m_leaked, n_per_band=20, seed=2, leak=True)
        + _simulate_responses(m_weak, n_per_band=20, seed=3)
    )

    reports = M.monitor_families([m_active, m_leaked, m_weak], resps)
    assert len(reports) == 3

    # Sorting: retired first, then flagged, then active
    assert reports[0].status == "retired"
    assert reports[1].status == "flagged"
    assert reports[2].status == "active"

    # JSON export structure
    d = reports[0].to_dict()
    assert d["id"] == "be.item.weak.v1"
    assert d["status"] == "retired"
    assert "low_discrimination" in d["flags"]
    assert len(d["bands"]) == 4
    for b in d["bands"]:
        assert "band" in b and "observed_rate" in b and "expected_rate" in b and "z_score" in b
