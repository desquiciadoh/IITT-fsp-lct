"""Pilot and annotation analysis (ML-14, AI-16): the checks that need real people.

Inputs are CSV files under validation/data/pilot/ (UTF-8, header row). They are collected during
the pilot and are not in the repo yet; until they exist every section reports
{"status": "no_data"} and nothing is estimated or filled in. Tests use synthetic fixtures in a
temporary directory only.

assessments.csv   person,known_grade,attempt,grade
                  known_grade: the grade the person holds by an external standard (a lead's
                  assessment, a passed interview loop); grade: what our test gave on that
                  attempt (1 or 2; attempt 2 is the retest). Grades: intern|junior|middle|senior.
annotations.csv   pair_id,annotator_a,annotator_b,oracle
                  two independent human relevance labels (0-3) for a (position, candidate) pair
                  and the synthetic oracle's relevance for the same pair (validation.bench_matching
                  .relevance). The target sample is 300 pairs.

Metrics:
  known grade vs result   exact and adjacent agreement, quadratic weighted κ (attempt 1 only)
  retest                  same grade on attempts 1 and 2, quadratic weighted κ between them
  annotators              quadratic weighted κ between annotator_a and annotator_b
  oracle vs human         Spearman ρ between the oracle and the mean human label
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from validation.sim_assessment import quadratic_weighted_kappa

PILOT_DIR = Path(__file__).resolve().parent / "data" / "pilot"
GRADES = ("intern", "junior", "middle", "senior")
TARGET_PAIRS = 300


class PilotDataError(ValueError):
    """A pilot file exists but is malformed. Raised, never skipped: a silently dropped row would
    change the reported agreement."""


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise PilotDataError(f"{path.name}: missing columns {missing}")
        rows = list(reader)
    if not rows:
        raise PilotDataError(f"{path.name}: no rows")
    return rows


def _grade(value: str, where: str) -> int:
    if value not in GRADES:
        raise PilotDataError(f"{where}: unknown grade {value!r}")
    return GRADES.index(value)


def _label(value: str, where: str) -> int:
    try:
        x = int(value)
    except ValueError as e:
        raise PilotDataError(f"{where}: label {value!r} is not an integer") from e
    if not 0 <= x <= 3:
        raise PilotDataError(f"{where}: label {x} is outside 0-3")
    return x


def spearman_rho(x: list[float], y: list[float]) -> float:
    """Spearman's ρ: Pearson r of average ranks (ties share their mean rank)."""
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("spearman_rho needs two equal-length samples of size >= 3")

    def ranks(v: list[float]) -> np.ndarray:
        a = np.asarray(v, float)
        order = np.argsort(a, kind="mergesort")
        r = np.empty(len(a))
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        raise ValueError("spearman_rho is undefined for a constant sample")
    return float(np.corrcoef(rx, ry)[0, 1])


def analyze_assessments(rows: list[dict[str, str]] | None) -> dict[str, Any]:
    if rows is None:
        return {"status": "no_data"}
    first: dict[str, tuple[int, int]] = {}
    second: dict[str, int] = {}
    for i, r in enumerate(rows, start=2):
        where = f"assessments.csv line {i}"
        known, got = _grade(r["known_grade"], where), _grade(r["grade"], where)
        attempt, person = r["attempt"].strip(), r["person"].strip()
        target = first if attempt == "1" else second if attempt == "2" else None
        if target is None:
            raise PilotDataError(f"{where}: attempt must be 1 or 2, got {attempt!r}")
        if person in target:
            raise PilotDataError(f"{where}: duplicate attempt {attempt} for {person!r}")
        if attempt == "1":
            first[person] = (known, got)
        else:
            second[person] = got
    known = [k for k, _ in first.values()]
    got = [g for _, g in first.values()]
    out: dict[str, Any] = {"status": "ok", "n": len(first),
                           "exact": round(float(np.mean([k == g for k, g in zip(known, got, strict=True)])), 4),
                           "adjacent": round(float(np.mean([abs(k - g) <= 1 for k, g in zip(known, got, strict=True)])), 4),
                           "qwk": round(quadratic_weighted_kappa(known, got), 4)}
    pairs = [(first[p][1], second[p]) for p in sorted(second) if p in first]
    orphans = sorted(set(second) - set(first))
    if orphans:
        raise PilotDataError(f"assessments.csv: retest without a first attempt for {orphans[:5]}")
    out["retest"] = ({"status": "no_data"} if not pairs else
                     {"status": "ok", "n": len(pairs),
                      "same_grade": round(float(np.mean([a == b for a, b in pairs])), 4),
                      "qwk": round(quadratic_weighted_kappa([a for a, _ in pairs], [b for _, b in pairs]), 4)})
    return out


def analyze_annotations(rows: list[dict[str, str]] | None) -> dict[str, Any]:
    if rows is None:
        return {"status": "no_data", "target_pairs": TARGET_PAIRS}
    a, b, oracle, seen = [], [], [], set()
    for i, r in enumerate(rows, start=2):
        where = f"annotations.csv line {i}"
        if r["pair_id"] in seen:
            raise PilotDataError(f"{where}: duplicate pair_id {r['pair_id']!r}")
        seen.add(r["pair_id"])
        a.append(_label(r["annotator_a"], where))
        b.append(_label(r["annotator_b"], where))
        try:
            oracle.append(float(r["oracle"]))
        except ValueError as e:
            raise PilotDataError(f"{where}: oracle {r['oracle']!r} is not a number") from e
    human = [(x + y) / 2 for x, y in zip(a, b, strict=True)]
    return {"status": "ok", "n": len(rows), "target_pairs": TARGET_PAIRS,
            "kappa_annotators": round(quadratic_weighted_kappa(a, b), 4),
            "spearman_oracle_human": round(spearman_rho(oracle, human), 4)}


def run_pilot_analysis(pilot_dir: Path = PILOT_DIR) -> dict[str, Any]:
    return {
        "assessments": analyze_assessments(_read(pilot_dir / "assessments.csv",
                                                 ("person", "known_grade", "attempt", "grade"))),
        "annotations": analyze_annotations(_read(pilot_dir / "annotations.csv",
                                                 ("pair_id", "annotator_a", "annotator_b", "oracle"))),
    }
