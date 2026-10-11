"""ML-11: leak and drift monitor + recalibration. Pure: no DB, fixed seeds, independent references."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest
from assessment.engine import monitor as M
from assessment.engine.content import load_content
from assessment.engine.irt import p_3pl
from assessment.families.base import FamilyMeta


def _meta(fid="be.test.item.v1", a=1.2, b=0.0, c=0.25) -> FamilyMeta:
    return FamilyMeta(id=fid, version=1, specs=("backend",), topic="backend.http", skills=("python",),
                      format="concept_mcq", a=a, b=b, c=c, time_limit_s=60)


def _examinees(rng: np.random.Generator, n: int, s: float = 0.4):
    """θ ~ N(0, 1) and an EAP-like estimate from a noisy measurement x = θ + N(0, s²): θ̂ = x/(1+s²),
    SE = s/√(1+s²). Then θ | θ̂ ~ N(θ̂, SE²) exactly, which is what the monitor assumes."""
    theta = rng.normal(0.0, 1.0, n)
    x = theta + rng.normal(0.0, s, n)
    return theta, x / (1 + s * s), np.full(n, s / math.sqrt(1 + s * s))


def _responses(meta, rng, n, true_a=None, true_b=None, s=0.4, cheat=None, session_prefix="s"):
    theta, est, se = _examinees(rng, n, s)
    p = p_3pl(theta, true_a or meta.a, meta.b if true_b is None else true_b, meta.c)
    u = rng.random(n) < p
    if cheat is not None:
        u = u | cheat(theta, rng)
    return [M.ItemResponse(meta.id, float(t), bool(c), float(e), f"{session_prefix}{i}")
            for i, (t, c, e) in enumerate(zip(est, u, se, strict=True))]


# ── constants and helpers ──────────────────────────────────────────────────

def test_band_cuts_match_the_grade_scale():
    cuts = load_content().band_cuts
    assert tuple(hi for _, _, hi in M.BAND_CUTS[:-1]) == tuple(cuts)
    assert M.STATUSES == ("active", "flagged", "retired")


def test_expected_p_with_zero_se_is_p_and_otherwise_the_posterior_mean():
    th = np.array([-1.0, 0.3, 2.0])
    assert M.expected_p(th, np.zeros(3), 1.2, 0.4, 0.25) == pytest.approx(p_3pl(th, 1.2, 0.4, 0.25), abs=1e-12)
    # reference: a fine Riemann sum of P(θ)·φ((θ − θ̂)/SE)
    grid = np.linspace(-10, 10, 200_001)
    for t, s in ((0.3, 0.5), (-1.2, 0.8)):
        w = np.exp(-0.5 * ((grid - t) / s) ** 2)
        ref = float(np.sum(p_3pl(grid, 1.4, 0.2, 0.2) * w) / np.sum(w))
        got = float(M.expected_p(np.array([t]), np.array([s]), 1.4, 0.2, 0.2)[0])
        assert got == pytest.approx(ref, abs=2e-4)


def test_benjamini_hochberg_textbook_example():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    assert M.benjamini_hochberg(p, 0.05) == [True, True] + [False] * 8
    assert M.benjamini_hochberg([0.01, 0.02, 0.03], 0.05) == [True, True, True]   # step-up, not step-down
    assert M.benjamini_hochberg([], 0.05) == []


# ── recalibration: against an independent grid MAP ────────────────────────

def _grid_map(theta, u, c, prior_a, prior_b):
    """Coarse-to-fine grid maximisation of the same log posterior, written out separately."""
    def logpost(a, b):
        z = a[..., None] * (theta[None, None, :] - b[..., None])
        p = np.clip(c + (1 - c) / (1 + np.exp(-z)), 1e-9, 1 - 1e-9)
        ll = np.sum(u * np.log(p) + (1 - u) * np.log(1 - p), axis=-1)
        return ll - 0.5 * ((np.log(a) - math.log(prior_a)) / 0.5) ** 2 - 0.5 * ((b - prior_b) / 1.5) ** 2

    best = (prior_a, prior_b)
    for width, step in ((None, 0.05), (0.15, 0.01), (0.03, 0.002)):
        if width is None:
            a_ax, b_ax = np.arange(0.2, 3.5, step), np.arange(-3.0, 3.0, step)
        else:
            a_ax = np.arange(best[0] - width, best[0] + width + 1e-12, step)
            b_ax = np.arange(best[1] - width, best[1] + width + 1e-12, step)
        A, B = np.meshgrid(a_ax, b_ax, indexing="ij")
        vals = np.concatenate([logpost(A[i:i + 8], B[i:i + 8]) for i in range(0, len(a_ax), 8)])
        i, j = np.unravel_index(int(np.argmax(vals)), vals.shape)
        best = (float(a_ax[i]), float(b_ax[j]))
    return best


@pytest.mark.parametrize("true_a, true_b, prior_a, prior_b, n, seed", [
    (1.2, 0.0, 1.2, 0.0, 2000, 1),
    (2.0, 1.0, 1.0, 0.0, 2000, 2),
    (1.0, -1.0, 1.0, 0.5, 2000, 3),
    (0.4, 0.5, 1.2, 0.0, 2000, 4),
])
def test_recalibration_matches_grid_map(true_a, true_b, prior_a, prior_b, n, seed):
    rng = np.random.default_rng(seed)
    theta = rng.normal(0, 1, n)
    u = (rng.random(n) < p_3pl(theta, true_a, true_b, 0.25)).astype(float)
    cal = M.recalibrate_family(theta, u, 0.25, prior_a=prior_a, prior_b=prior_b)
    ga, gb = _grid_map(theta, u, 0.25, prior_a, prior_b)
    assert cal.converged
    assert cal.a == pytest.approx(ga, abs=0.01) and cal.b == pytest.approx(gb, abs=0.01)
    # and it recovers the truth within a few standard errors
    assert abs(cal.a - true_a) < 4 * cal.se_a + 0.05 and abs(cal.b - true_b) < 4 * cal.se_b + 0.05


def test_recalibration_does_not_depend_on_the_iteration_cap_once_converged():
    """The first version oscillated: max_iter 24/25 gave (1.2, 0) / (0.9, 0.3) at n = 5000."""
    rng = np.random.default_rng(11)
    theta = rng.normal(0, 1, 5000)
    u = (rng.random(5000) < p_3pl(theta, 1.2, 0.0, 0.25)).astype(float)
    results = {(round(c.a, 6), round(c.b, 6)) for c in
               (M.recalibrate_family(theta, u, 0.25, 1.2, 0.0, max_iter=k) for k in (24, 25, 26, 200))}
    assert len(results) == 1


# ── decisions ──────────────────────────────────────────────────────────────

def test_well_specified_pool_is_rarely_flagged():
    """40 correct families, θ̂ with SE ≈ 0.37: with the posterior expectation and FDR control at
    most a couple of false flags over 3 runs (the first version flagged ~15 % per run)."""
    flagged = 0
    for seed in range(3):
        rng = np.random.default_rng(100 + seed)
        metas = [_meta(f"t.fam.f{i}.v1", a=float(rng.uniform(0.9, 1.6)), b=float(rng.uniform(-1.5, 1.5)))
                 for i in range(40)]
        resp = [r for m in metas for r in _responses(m, rng, int(rng.integers(100, 1200)), session_prefix=m.id)]
        reports = M.monitor_families(metas, resp)
        flagged += sum(1 for rep in reports if rep.drift_flag)
        assert not any(rep.status == "retired" for rep in reports)
    assert flagged <= 2


def test_leak_on_a_hard_item_is_found_below_the_item_not_only_in_junior_bands():
    """b = 1.3: the middle band is below the item; 20 % of examinees there answer from a leaked key."""
    meta = _meta(a=1.3, b=1.3, c=0.0)
    rng = np.random.default_rng(5)
    leak = _responses(meta, rng, 1500, cheat=lambda th, r: (th < 1.3) & (r.random(th.shape) < 0.2))
    rep = M.analyze_family(meta, leak)
    assert "leak_suspected" in rep.flags and rep.status == "flagged"
    honest = M.analyze_family(meta, _responses(meta, np.random.default_rng(6), 1500))
    assert honest.flags == [] and honest.status == "active"


def test_content_drift_when_the_item_got_harder():
    meta = _meta(a=1.2, b=0.0)
    rep = M.analyze_family(meta, _responses(meta, np.random.default_rng(7), 1200, true_b=0.8))
    assert "content_drift" in rep.flags and "leak_suspected" not in rep.flags
    assert rep.calibrated_b == pytest.approx(0.8, abs=0.3)          # recalibration sees the shift


def test_low_discrimination_after_calibration_retires_but_an_authored_low_a_only_flags():
    meta = _meta(a=1.2, b=0.0)
    flat = M.analyze_family(meta, _responses(meta, np.random.default_rng(8), 3000, true_a=0.25))
    assert flat.status == "retired" and "low_discrimination" in flat.flags
    assert flat.calibrated_a + 1.96 * flat.calibrated_se_a < 0.6

    authored = _meta(a=0.5, b=0.0)
    rep = M.analyze_family(authored, [])
    assert rep.status == "flagged" and rep.flags == ["low_discrimination_prior"]


def test_a_correct_a08_family_is_not_retired():
    """The review measured 83 / 200 false retirements of an a = 0.8 family with the old optimiser."""
    retired = 0
    for seed in range(60):
        meta = _meta(a=0.8, b=0.0)
        rng = np.random.default_rng(1000 + seed)
        rep = M.analyze_family(meta, _responses(meta, rng, int(rng.integers(200, 3000))))
        retired += rep.status == "retired"
    assert retired == 0


def test_small_samples_are_not_tested_or_calibrated():
    meta = _meta()
    rep = M.analyze_family(meta, _responses(meta, np.random.default_rng(9), 25))
    assert rep.p_leak == 1.0 and rep.p_drift == 1.0          # every band < 20, total < 30
    assert rep.calibrated_a is None and rep.status == "active"


def test_exposure_is_the_share_of_sessions_and_reports_serialise():
    a, b = _meta("t.fam.a.v1"), _meta("t.fam.b.v1")
    resp = [M.ItemResponse(a.id, 0.0, True, 0.3, "s1"), M.ItemResponse(b.id, 0.0, False, 0.3, "s1"),
            M.ItemResponse(a.id, 0.5, True, 0.3, "s2"), M.ItemResponse(a.id, -0.5, False, 0.3, "s3")]
    reports = {r.family_id: r for r in M.monitor_families([a, b], resp)}
    assert reports[a.id].exposure_rate == pytest.approx(1.0)
    assert reports[b.id].exposure_rate == pytest.approx(1 / 3)
    d = reports[a.id].to_dict()
    json.dumps(d)
    assert d["id"] == a.id and d["exposures"] == 3 and len(d["bands"]) == 4
