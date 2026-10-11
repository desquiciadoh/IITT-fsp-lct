"""Assessment simulation (ML-8, AI-10 part 2; ARCHITECTURE §2.12, targets §5.3). Pure: no Django.

Simulees with θ ~ N(0, 1) take the production `IrtCatEngine`; they answer with the *true* item
parameters (the authored ones perturbed once per seed, `simulate.perturbed_params`), so the engine
is not tested against its own assumptions. The response model is unidimensional here: grade
accuracy is about θ (the synthetic world adds skill exposure, see synth.py). Measured:

- exact / adjacent grade accuracy, the confusion matrix (rows: band of θ, columns: result grade), QWK;
- retest: a second independent session (same claim, no excluded families) per simulee of a subset,
  same-grade share and Pearson r of θ̂;
- median length, the share of sessions ending at the 20-item cap, and the maximum family
  exposure per specialisation (share of that spec's sessions that served the family);
- the engine's mean test information function over administered items;
- collision rate and generator errors from the verify harness on every family (n per family);
- the leak attack (see `leak_attack`);
- recovery of item parameters by the ML-11 recalibration (fixed-θ MAP) from simulated responses.
"""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np
from assessment.engine.cat import IrtCatEngine
from assessment.engine.content import Content, load_content
from assessment.engine.irt import information
from assessment.engine.monitor import recalibrate_family
from assessment.engine.policy import band_of
from assessment.families import verify as harness
from assessment.families.base import GRADES, SPECS, FamilyMeta
from assessment.families.registry import active_metas, all_families, make_rng

from validation.simulate import SECRET, TrueParams, p_correct, perturbed_params, run_session

SPEC_SHARE = {"backend": 0.45, "frontend": 0.35, "ml_data": 0.20}
TIF_THETA_GRID = [round(-3.0 + 0.5 * i, 1) for i in range(13)]
LEAK_SHARES = (0.1, 0.3, 0.5)
MAX_ITEMS = 20


# ── metrics ────────────────────────────────────────────────────────────────

def quadratic_weighted_kappa(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int = 4) -> float:
    """Cohen's kappa with quadratic weights (i − j)² / (k − 1)²."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length")
    if not y_true:
        raise ValueError("QWK of an empty sample is undefined")
    obs = np.zeros((n_classes, n_classes))
    for t, p in zip(y_true, y_pred, strict=True):
        obs[t, p] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(axis=1), obs.sum(axis=0))
    idx = np.arange(n_classes)
    w = (idx[:, None] - idx[None, :]) ** 2 / (n_classes - 1) ** 2
    den = float((w * exp).sum())
    return 1.0 - float((w * obs).sum()) / den if den else 1.0


def pearson_r(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("pearson_r needs two equal-length samples of size >= 2")
    return float(np.corrcoef(np.asarray(x, float), np.asarray(y, float))[0, 1])


# ── grade accuracy, retest, length, exposure, TIF ─────────────────────────

def _simulees(n: int, seed: int, content: Content):
    rng = random.Random(f"simulees|{seed}")
    out = []
    for i in range(n):
        spec = rng.choices(SPECS, weights=[SPEC_SHARE[s] for s in SPECS])[0]
        theta = rng.gauss(0.0, 1.0)
        claimed = band_of(theta + rng.gauss(0.0, 0.35), content)      # claims are roughly right
        out.append((f"sim-{seed}-{i:06d}", spec, theta, claimed))
    return out


def grade_accuracy(n: int, seed: int, retest_n: int, pools, true_params, content: Content) -> dict[str, Any]:
    engine = IrtCatEngine()
    confusion = [[0] * 4 for _ in range(4)]
    truth_idx, result_idx, lengths, stop = [], [], [], Counter()
    served_by_spec: dict[str, Counter] = {s: Counter() for s in SPECS}
    sessions_by_spec: Counter = Counter()
    grid = np.asarray(TIF_THETA_GRID)
    tif = np.zeros_like(grid)
    retest_1, retest_2, retest_same = [], [], 0
    metas = {m.id: m for spec in SPECS for m in pools[spec]}
    for k, (sid, spec, theta, claimed) in enumerate(_simulees(n, seed, content)):
        out = run_session(engine, pools[spec], true_params, spec, claimed, theta, sid)
        t, r = GRADES.index(band_of(theta, content)), GRADES.index(out.result.result_grade)
        confusion[t][r] += 1
        truth_idx.append(t)
        result_idx.append(r)
        lengths.append(len(out.families))
        stop[out.result.stop_reason or "none"] += 1
        sessions_by_spec[spec] += 1
        served_by_spec[spec].update(set(out.families))
        for fid in out.families:
            m = metas[fid]
            tif += information(grid, m.a, m.b, m.c)
        if k < retest_n:
            again = run_session(engine, pools[spec], true_params, spec, claimed, theta, f"{sid}-retest")
            retest_1.append(out.result.theta)
            retest_2.append(again.result.theta)
            retest_same += again.result.result_grade == out.result.result_grade
    exposure = {spec: max(served_by_spec[spec].values()) / sessions_by_spec[spec]
                for spec in SPECS if sessions_by_spec[spec]}
    exact = sum(confusion[i][i] for i in range(4)) / n
    adjacent = sum(confusion[i][j] for i in range(4) for j in range(4) if abs(i - j) <= 1) / n
    return {
        "simulees": n, "exact_acc": exact, "adjacent_acc": adjacent,
        "qwk": quadratic_weighted_kappa(truth_idx, result_idx), "confusion": confusion,
        "retest_same_grade": retest_same / retest_n, "retest_r": pearson_r(retest_1, retest_2),
        "median_len": float(statistics.median(lengths)), "max_family_exposure": max(exposure.values()),
        "tif": {"theta": TIF_THETA_GRID, "info": [round(float(x), 4) for x in tif / n]},
        "_details": {"retest_n": retest_n, "exposure_by_spec": exposure,
                     "share_at_max_items": sum(1 for x in lengths if x >= MAX_ITEMS) / n,
                     "stop_reasons": dict(sorted(stop.items()))},
    }


# ── bank quality from the verify harness ───────────────────────────────────

def bank_quality(n_per_family: int) -> dict[str, Any]:
    """Collision rate over the families the collision gate applies to (parametric families), and
    generator errors over all families. Concept (classification) families are reported apart:
    they have a handful of questions by design (ML.md D14)."""
    reports = harness.verify_all(n=n_per_family)
    gated = [r for r in reports if r.collision_gated]
    instances = sum(r.n for r in gated)
    duplicates = sum(round(r.collision_rate * r.n) for r in gated)
    errors = sum(int(e.rsplit("[x", 1)[1].rstrip("]")) if "[x" in e else 1
                 for r in reports for e in r.errors if e.startswith("generate:"))
    return {"collision_rate": duplicates / instances if instances else 0.0, "generator_errors": errors,
            "_details": {"n_per_family": n_per_family, "families": len(reports),
                         "failing_families": [r.family_id for r in reports if not r.ok],
                         "concept_collision_rates": {r.family_id: r.collision_rate for r in reports
                                                     if not r.collision_gated},
                         "max_parametric_collision_rate": max((r.collision_rate for r in gated), default=0.0)}}


# ── leak attack ────────────────────────────────────────────────────────────

LEAKED_INSTANCES = 20      # instances of a leaked family the cheater holds (a scraped answer sheet)


def key_reuse(fam, leaked: int = LEAKED_INSTANCES, trials: int = 200) -> float:
    """P(a fresh instance is the same question as one of `leaked` leaked instances). Same semantic
    fingerprint means same answer (the verify harness checks it), so the cheater answers it right;
    any other instance is a new question and the leaked answers do not help."""
    held = {fam.generate(make_rng(SECRET, "leak-held", fam.meta.id, i)).fingerprint for i in range(leaked)}
    return sum(fam.generate(make_rng(SECRET, "leak-new", fam.meta.id, i)).fingerprint in held
               for i in range(trials)) / trials


def leak_attack(pool: list[FamilyMeta], true_params: dict[str, TrueParams], spec: str, n: int, seed: int,
                draws: int, content: Content) -> dict[str, Any]:
    """Cheaters who hold the answers of a share of the bank. Static bank: a leaked item is always
    answered right. Parametric families: the cheater holds LEAKED_INSTANCES instances of each
    leaked family; a fresh instance that is the same question as one of them is answered right
    (probability `key_reuse`), any other is answered honestly. The honest run and both attacks
    share each simulee's session id (common random numbers), the leaked sets are nested prefixes of
    one permutation, and the result is averaged over `draws` permutations."""
    engine = IrtCatEngine()
    registry = all_families()
    reuse = {m.id: key_reuse(registry[m.id]) for m in pool}
    rng = random.Random(f"leak|{seed}")
    people = [(f"leak-{seed}-{i:05d}", rng.gauss(0.0, 1.0)) for i in range(n)]
    ids = sorted(m.id for m in pool)
    rows, details = [], []
    for share in LEAK_SHARES:
        d_static, d_param, promo_static, promo_param, promo_honest = [], [], 0, 0, 0
        for draw in range(draws):
            order = random.Random(f"leak-perm|{seed}|{draw}").sample(ids, len(ids))
            leaked = set(order[:max(1, round(share * len(ids)))])
            for sid, theta in people:
                claimed = band_of(theta + 1.0, content)          # cheaters claim one band up
                truth = GRADES.index(band_of(theta, content))
                sess = f"{sid}|{draw}"
                honest = run_session(engine, pool, true_params, spec, claimed, theta, sess)

                def static(meta, p, ok, leaked=leaked):
                    return True if meta.id in leaked else None

                choice_rng = random.Random(f"cheat|{sess}|{share}")

                def parametric(meta, p, ok, leaked=leaked, r=choice_rng):
                    if meta.id not in leaked:
                        return None
                    return True if r.random() < reuse[meta.id] else None

                st = run_session(engine, pool, true_params, spec, claimed, theta, sess, answer_override=static)
                pa = run_session(engine, pool, true_params, spec, claimed, theta, sess, answer_override=parametric)
                d_static.append(st.result.theta - honest.result.theta)
                d_param.append(pa.result.theta - honest.result.theta)
                promo_honest += GRADES.index(honest.result.result_grade) > truth
                promo_static += GRADES.index(st.result.result_grade) > truth
                promo_param += GRADES.index(pa.result.result_grade) > truth
        m = len(d_static)
        rows.append({"leak_share": share, "static_dtheta": round(statistics.fmean(d_static), 4),
                     "parametric_dtheta": round(statistics.fmean(d_param), 4)})
        details.append({"leak_share": share, "sessions": m,
                        "static_dtheta_se": statistics.stdev(d_static) / math.sqrt(m),
                        "parametric_dtheta_se": statistics.stdev(d_param) / math.sqrt(m),
                        "over_graded_honest": promo_honest / m, "over_graded_static": promo_static / m,
                        "over_graded_parametric": promo_param / m})
    return {"rows": rows, "_details": {"spec": spec, "simulees": n, "draws": draws, "per_share": details,
                                       "leaked_instances_per_family": LEAKED_INSTANCES,
                                       "same_question_probability": dict(sorted(reuse.items()))}}


# ── calibration recovery ───────────────────────────────────────────────────

def calibration_recovery(metas: list[FamilyMeta], true_params: dict[str, TrueParams], seed: int,
                         n_responses: int = 600, se: float = 0.35) -> dict[str, Any]:
    """Can the ML-11 recalibration recover the true parameters from the authored priors? For each
    family: n responses from θ ~ N(0, 1) with the true parameters, θ̂ = EAP-like estimate with
    standard error `se`, then fixed-θ MAP. RMSE of a and b, before (authored) and after."""
    rng = np.random.default_rng(seed)
    shrink = 1 / (1 + se * se)
    post_sd = se * math.sqrt(shrink)            # SD of θ given the EAP-like estimate
    rows = []
    for m in sorted(metas, key=lambda m: m.id):
        t = true_params[m.id]
        theta = rng.normal(0, 1, n_responses)
        est = (theta + rng.normal(0, se, n_responses)) * shrink
        u = (rng.random(n_responses) < np.array([p_correct(x, t) for x in theta])).astype(float)
        cal = recalibrate_family(est, u, m.c, prior_a=m.a, prior_b=m.b, ses=np.full(n_responses, post_sd))
        rows.append((m.a - t.a, m.b - t.b, cal.a - t.a, cal.b - t.b, cal.converged))

    def rmse(k):
        return math.sqrt(statistics.fmean(r[k] ** 2 for r in rows))
    return {"families": len(rows), "n_responses": n_responses, "theta_se": se,
            "rmse_a_prior": rmse(0), "rmse_b_prior": rmse(1), "rmse_a_calibrated": rmse(2),
            "rmse_b_calibrated": rmse(3), "converged": sum(r[4] for r in rows)}


# ── entry point ────────────────────────────────────────────────────────────

def run_assessment_simulation(n_simulees: int = 10_000, seed: int = 2026, retest_n: int = 2_500,
                              leak_n: int = 300, leak_draws: int = 2, verify_n: int = 1_000,
                              content: Content | None = None) -> dict[str, Any]:
    """The `assessment` block of report.json, plus `_details` for validation/out/details.json."""
    content = content or load_content()
    pools = {spec: active_metas(spec) for spec in SPECS}
    metas = sorted({m.id: m for spec in SPECS for m in pools[spec]}.values(), key=lambda m: m.id)
    true_params = perturbed_params(metas, seed=seed)
    grades = grade_accuracy(n_simulees, seed, min(retest_n, n_simulees), pools, true_params, content)
    bank = bank_quality(verify_n)
    leak = leak_attack(pools["backend"], true_params, "backend", leak_n, seed, leak_draws, content)
    calib = [calibration_recovery(metas, true_params, seed, n_responses=n) for n in (200, 600, 2000)]
    out = {k: v for k, v in grades.items() if k != "_details"}
    out.update(collision_rate=bank["collision_rate"], generator_errors=bank["generator_errors"],
               leak_attack=leak["rows"])
    for k in ("exact_acc", "adjacent_acc", "qwk", "retest_same_grade", "retest_r", "max_family_exposure",
              "collision_rate"):
        out[k] = round(float(out[k]), 4)
    out["_details"] = {"grades": grades["_details"], "bank": bank["_details"], "leak": leak["_details"],
                       "calibration": calib}
    return out
