"""ValidationReport schema (TASKS.md §1.4; ML-5). Pure: no Django.

`validate_report(d)` returns a list of errors (empty = valid): exact key sets, types and ranges.
BE serves validation/out/report.json (else report.fixture.json) at GET /api/lab/report; FE2
renders it and shows a FIXTURE banner when `synthetic_fixture` is true.

    type ValidationReport = { generated_at: string; git_sha: string; synthetic_fixture: boolean
      assessment: { simulees; exact_acc; adjacent_acc; qwk; retest_same_grade; retest_r; median_len;
        max_family_exposure; collision_rate; generator_errors; confusion: number[][]
        tif: { theta: number[]; info: number[] }
        leak_attack: { leak_share; static_dtheta; parametric_dtheta }[] }
      matching: { candidates; needs; non_fsp_parity; pool_p95_ms
        systems: { name; ndcg10; p10; r50; mrr }[] } }
"""
from __future__ import annotations

import math
from typing import Any

TOP_KEYS = {"generated_at", "git_sha", "synthetic_fixture", "assessment", "matching"}
ASSESSMENT_KEYS = {"simulees", "exact_acc", "adjacent_acc", "qwk", "retest_same_grade", "retest_r",
                   "median_len", "max_family_exposure", "collision_rate", "generator_errors",
                   "confusion", "tif", "leak_attack"}
TIF_KEYS = {"theta", "info"}
LEAK_KEYS = {"leak_share", "static_dtheta", "parametric_dtheta"}
MATCHING_KEYS = {"candidates", "needs", "non_fsp_parity", "pool_p95_ms", "systems"}
SYSTEM_KEYS = {"name", "ndcg10", "p10", "r50", "mrr"}
N_GRADES = 4

# fields that are shares or correlations in [0, 1] (retest_r and qwk may be negative in theory)
UNIT_FIELDS = {"exact_acc", "adjacent_acc", "retest_same_grade", "max_family_exposure", "collision_rate"}
SIGNED_UNIT_FIELDS = {"qwk", "retest_r"}


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _keys(obj: Any, expected: set[str], where: str, errs: list[str]) -> bool:
    if not isinstance(obj, dict):
        errs.append(f"{where}: expected an object")
        return False
    missing, extra = sorted(expected - set(obj)), sorted(set(obj) - expected)
    if missing:
        errs.append(f"{where}: missing {missing}")
    if extra:
        errs.append(f"{where}: unexpected {extra}")
    return not missing


def validate_report(d: Any) -> list[str]:
    errs: list[str] = []
    if not _keys(d, TOP_KEYS, "report", errs):
        return errs
    if not isinstance(d["generated_at"], str) or not d["generated_at"]:
        errs.append("generated_at: expected an ISO 8601 string")
    if not isinstance(d["git_sha"], str) or not d["git_sha"]:
        errs.append("git_sha: expected a non-empty string")
    if not isinstance(d["synthetic_fixture"], bool):
        errs.append("synthetic_fixture: expected a boolean")

    a = d["assessment"]
    if _keys(a, ASSESSMENT_KEYS, "assessment", errs):
        for k in ASSESSMENT_KEYS - {"confusion", "tif", "leak_attack"}:
            if not _num(a[k]):
                errs.append(f"assessment.{k}: expected a finite number")
            elif k in UNIT_FIELDS and not 0 <= a[k] <= 1:
                errs.append(f"assessment.{k}: {a[k]} outside [0, 1]")
            elif k in SIGNED_UNIT_FIELDS and not -1 <= a[k] <= 1:
                errs.append(f"assessment.{k}: {a[k]} outside [-1, 1]")
        for k in ("simulees", "generator_errors"):
            if _num(a[k]) and (a[k] < 0 or a[k] != int(a[k])):
                errs.append(f"assessment.{k}: expected a non-negative integer")
        conf = a["confusion"]
        if (not isinstance(conf, list) or len(conf) != N_GRADES
                or any(not isinstance(r, list) or len(r) != N_GRADES or not all(_num(v) and v >= 0 for v in r)
                       for r in conf)):
            errs.append("assessment.confusion: expected a 4x4 matrix of non-negative counts")
        if _keys(a["tif"], TIF_KEYS, "assessment.tif", errs):
            th, info = a["tif"]["theta"], a["tif"]["info"]
            if not (isinstance(th, list) and isinstance(info, list) and len(th) == len(info) and th
                    and all(_num(x) for x in th + info)):
                errs.append("assessment.tif: theta and info must be equal-length non-empty number lists")
        if not isinstance(a["leak_attack"], list) or not a["leak_attack"]:
            errs.append("assessment.leak_attack: expected a non-empty list")
        else:
            for i, row in enumerate(a["leak_attack"]):
                if _keys(row, LEAK_KEYS, f"assessment.leak_attack[{i}]", errs) and not all(
                        _num(row[k]) for k in LEAK_KEYS):
                    errs.append(f"assessment.leak_attack[{i}]: expected numbers")

    m = d["matching"]
    if _keys(m, MATCHING_KEYS, "matching", errs):
        for k in ("candidates", "needs", "non_fsp_parity", "pool_p95_ms"):
            if not _num(m[k]) or m[k] < 0:
                errs.append(f"matching.{k}: expected a non-negative number")
        if not isinstance(m["systems"], list) or not m["systems"]:
            errs.append("matching.systems: expected a non-empty list")
        else:
            for i, row in enumerate(m["systems"]):
                if not _keys(row, SYSTEM_KEYS, f"matching.systems[{i}]", errs):
                    continue
                if not isinstance(row["name"], str) or not row["name"]:
                    errs.append(f"matching.systems[{i}].name: expected a string")
                for k in SYSTEM_KEYS - {"name"}:
                    if not _num(row[k]) or not 0 <= row[k] <= 1:
                        errs.append(f"matching.systems[{i}].{k}: expected a number in [0, 1]")
    return errs
