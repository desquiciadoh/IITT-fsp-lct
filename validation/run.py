"""python -m validation.run: the whole validation suite (ML-8). Pure: no Django.

1. assessment simulation (sim_assessment), 2. matching benchmark (bench_matching),
3. report.json (schema-validated, with the git SHA), details.json (everything the fixed schema has no
room for: misses, base rates, standard errors, calibration recovery), and SVG charts.

Every ARCHITECTURE §5.3 target is printed as PASS or MISS; the run never claims success it did not
measure. The exit code is 0 when the suite ran (misses are results, not crashes).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from validation.bench_matching import run_matching_benchmark
from validation.charts import generate_all_charts
from validation.pilot import run_pilot_analysis
from validation.report import build_report, git_sha, write_json
from validation.sim_assessment import run_assessment_simulation

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "validation" / "out"


def targets(a: dict, m: dict) -> list[dict]:
    """ARCHITECTURE §5.3 targets against the measured values."""
    by = {s["name"]: s for s in m["systems"]}
    ours, keyword, ablated = by["ours"], by["keyword"], by["ours_no_verified"]
    leak_ok = all(abs(r["parametric_dtheta"]) <= 0.1 for r in a["leak_attack"])
    leak_big = max(r["static_dtheta"] for r in a["leak_attack"])
    rows = [
        ("generator errors", a["generator_errors"], "= 0", a["generator_errors"] == 0),
        ("instance collision rate (parametric families)", a["collision_rate"], "<= 0.001", a["collision_rate"] <= 0.001),
        ("exact grade accuracy", a["exact_acc"], ">= 0.80", a["exact_acc"] >= 0.80),
        ("adjacent grade accuracy", a["adjacent_acc"], ">= 0.98", a["adjacent_acc"] >= 0.98),
        ("retest same grade", a["retest_same_grade"], ">= 0.80", a["retest_same_grade"] >= 0.80),
        ("retest r", a["retest_r"], ">= 0.85", a["retest_r"] >= 0.85),
        ("leak: parametric |dtheta| at every share", max(abs(r["parametric_dtheta"]) for r in a["leak_attack"]),
         "<= 0.10 (static large)", leak_ok and leak_big >= 0.3),
        ("median test length", a["median_len"], "<= 14", a["median_len"] <= 14),
        ("max family exposure (per spec)", a["max_family_exposure"], "<= 0.5", a["max_family_exposure"] <= 0.5),
        ("nDCG@10 (ours)", ours["ndcg10"], ">= 0.80", ours["ndcg10"] >= 0.80),
        ("P@10 (ours)", ours["p10"], ">= 0.80", ours["p10"] >= 0.80),
        ("lift over keyword (nDCG@10)", round(ours["ndcg10"] - keyword["ndcg10"], 4), "> 0",
         ours["ndcg10"] > keyword["ndcg10"]),
        ("ablation: verified evidence on - off (nDCG@10)", round(ours["ndcg10"] - ablated["ndcg10"], 4), "> 0",
         ours["ndcg10"] > ablated["ndcg10"]),
        ("non-FSP exposure parity", m["non_fsp_parity"], ">= 0.80", m["non_fsp_parity"] >= 0.80),
        ("pool scoring p95, ms (engine only)", m["pool_p95_ms"], "< 300", m["pool_p95_ms"] < 300),
    ]
    return [{"metric": k, "value": v, "target": t, "status": "PASS" if ok else "MISS"} for k, v, t, ok in rows]


def run(n_simulees: int, retest_n: int, leak_n: int, leak_draws: int, verify_n: int, n_positions: int,
        seed: int, out_dir: Path) -> dict:
    sha = git_sha()                                  # fail before an hour of work, not after
    t0 = time.perf_counter()
    print(f"[1/2] assessment: {n_simulees:,} simulees, retest {retest_n:,}, leak {leak_n} x {leak_draws}, "
          f"verify n={verify_n} (seed {seed})", flush=True)
    assessment = run_assessment_simulation(n_simulees, seed, retest_n, leak_n, leak_draws, verify_n)
    t1 = time.perf_counter()
    print(f"      {t1 - t0:.0f} s", flush=True)
    print(f"[2/2] matching: {n_positions} positions", flush=True)
    matching = run_matching_benchmark(n_positions)
    t2 = time.perf_counter()
    print(f"      {t2 - t1:.0f} s", flush=True)

    a_details, m_details = assessment.pop("_details"), matching.pop("_details")
    report = build_report(assessment, matching, sha)
    table = targets(assessment, matching)
    details = {"generated_at": report["generated_at"], "git_sha": sha, "seed": seed,
               "runtime_s": {"assessment": round(t1 - t0, 1), "matching": round(t2 - t1, 1)},
               "targets": table, "assessment": a_details, "matching": m_details,
               "pilot": run_pilot_analysis()}
    write_json(report, out_dir / "report.json")
    write_json(details, out_dir / "details.json")
    charts = generate_all_charts(report, out_dir / "charts")

    print(f"\n{'metric':<48} {'value':>10}  {'target':<24} status")
    for row in table:
        value = row["value"]
        shown = f"{value:.4f}" if isinstance(value, float) else str(value)
        print(f"{row['metric']:<48} {shown:>10}  {row['target']:<24} {row['status']}")
    print("\nsystems:  " + "  ".join(f"{s['name']} nDCG@10 {s['ndcg10']:.3f} P@10 {s['p10']:.3f}"
                                     for s in matching["systems"]))
    misses = sum(r["status"] == "MISS" for r in table)
    print(f"\n{len(table) - misses} targets met, {misses} missed; total {time.perf_counter() - t0:.0f} s")
    print(f"wrote {out_dir / 'report.json'}, {out_dir / 'details.json'} and {len(charts)} charts")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the validation suite (make validate).")
    ap.add_argument("--simulees", type=int, default=10_000)
    ap.add_argument("--retest", type=int, default=2_500)
    ap.add_argument("--leak", type=int, default=300, help="simulees per leak share")
    ap.add_argument("--leak-draws", type=int, default=2, help="leaked-set permutations to average over")
    ap.add_argument("--verify-n", type=int, default=1_000, help="instances per family for collisions")
    ap.add_argument("--positions", type=int, default=60)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--fast", action="store_true", help="smoke run: 500 simulees, small leak and verify samples")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    if args.fast:
        args.simulees, args.retest, args.leak, args.leak_draws, args.verify_n, args.positions = 500, 200, 40, 1, 100, 10
    run(args.simulees, args.retest, args.leak, args.leak_draws, args.verify_n, args.positions, args.seed,
        args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
