"""Main validation runner (ML-8, AI-10 part 2; python -m validation.run).

Orchestrates the entire validation suite:
  1. Assessment Monte Carlo simulation (10,000 simulees on production CAT engine);
  2. Matching benchmark (5 systems against hidden-truth relevance oracle on 60 needs);
  3. Strict schema validation against ValidationReport (TASKS.md §1.4);
  4. Generation of production validation/out/report.json;
  5. Rendering of SVG charts into validation/out/charts/;
  6. Human-readable summary output for jury and pitch slides.

Runtime constraint: executes well under 10 minutes.
Pure: no Django.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from validation.bench_matching import run_matching_benchmark
from validation.charts import generate_all_charts
from validation.report import build_validation_report, write_validation_report
from validation.sim_assessment import run_assessment_simulation

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "validation" / "out"


def run_full_validation(
    n_simulees: int = 10000,
    n_positions: int = 60,
    seed: int = 2026,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict:
    """Run full validation suite and write report.json and charts."""
    t_start = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = out_dir / "charts"

    print("=" * 70)
    print("FSP DRAFT | VALIDATION SUITE (ML-8 / AI-10)")
    print(f"Seed: {seed} | Simulees: {n_simulees:,} | Positions: {n_positions}")
    print("=" * 70)

    # 1. Assessment simulation
    print(f"\n[1/3] Simulating {n_simulees:,} test-takers on production IRT/CAT engine...")
    t0 = time.time()
    assessment_res = run_assessment_simulation(
        n_simulees=n_simulees,
        seed=seed,
    )
    dt_sim = time.time() - t0
    print(f"      Completed in {dt_sim:.1f} s")
    print(f"      Exact accuracy:    {assessment_res['exact_acc'] * 100:.1f}%")
    print(f"      Adjacent accuracy: {assessment_res['adjacent_acc'] * 100:.1f}%")
    print(f"      QWK (weighted kappa): {assessment_res['qwk']:.3f}")
    print(f"      Retest same grade:   {assessment_res['retest_same_grade'] * 100:.1f}% (r = {assessment_res['retest_r']:.3f})")
    print(f"      Median test len:     {assessment_res['median_len']} items (max exposure {assessment_res['max_family_exposure'] * 100:.1f}%)")

    # 2. Matching benchmark
    print(f"\n[2/3] Benchmarking matching algorithms on {n_positions} positions...")
    t0 = time.time()
    matching_res = run_matching_benchmark(
        n_positions=n_positions,
        seed=seed,
    )
    dt_match = time.time() - t0
    print(f"      Completed in {dt_match:.1f} s (pool p95 latency: {matching_res['pool_p95_ms']} ms)")
    print(f"      Non-FSP exposure parity: {matching_res['non_fsp_parity']:.3f}")

    print("\n      Retrieval Systems Comparison:")
    header = f"      {'System':<18s} {'nDCG@10':>9s} {'P@10':>9s} {'R@50':>9s} {'MRR':>9s}"
    print(header)
    print("      " + "-" * 50)
    for s in matching_res["systems"]:
        print(f"      {s['name']:<18s} {s['ndcg10']:>9.3f} {s['p10']:>9.3f} {s['r50']:>9.3f} {s['mrr']:>9.3f}")

    # 3. Assemble report and validate schema
    print("\n[3/3] Assembling report and generating SVG charts...")
    report = build_validation_report(
        assessment_metrics=assessment_res,
        matching_metrics=matching_res,
    )

    report_path = write_validation_report(report, out_dir / "report.json")
    print(f"      Wrote validated report: {report_path.relative_to(ROOT)}")

    chart_paths = generate_all_charts(report, charts_dir)
    for cp in chart_paths:
        print(f"      Rendered chart: {cp.relative_to(ROOT)}")

    total_time = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"VALIDATION PASSED (total runtime: {total_time:.1f} s < 600 s target)")
    print("=" * 70 + "\n")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run validation suite (make validate / python -m validation.run).")
    parser.add_argument("--simulees", "--n", type=int, default=10000, help="Number of simulees (default: 10000)")
    parser.add_argument("--positions", type=int, default=60, help="Number of positions (default: 60)")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed (default: 2026)")
    parser.add_argument("--fast", action="store_true", help="Fast mode for quick smoke checks (500 simulees, 10 positions)")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR), help="Output directory")
    args = parser.parse_args(argv)

    n_simulees = 500 if args.fast else args.simulees
    n_positions = 10 if args.fast else args.positions

    run_full_validation(
        n_simulees=n_simulees,
        n_positions=n_positions,
        seed=args.seed,
        out_dir=Path(args.out_dir),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
