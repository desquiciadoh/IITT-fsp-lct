"""ML-5: the report fixture matches ValidationReport in TASKS.md §1.4 exactly."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from validation import schema

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "validation" / "out" / "report.fixture.json"


def _ts_type() -> str:
    text = (ROOT / "docs" / "TASKS.md").read_text(encoding="utf-8")
    start = text.index("type ValidationReport = {")
    return text[start: text.index("```", start)]


def _ts_keys(block: str) -> set[str]:
    return set(re.findall(r"([a-z_0-9]+)\??:", block))


def test_schema_constants_match_the_typescript_contract():
    ts = _ts_type()
    declared = (schema.TOP_KEYS | schema.ASSESSMENT_KEYS | schema.TIF_KEYS | schema.LEAK_KEYS
                | schema.MATCHING_KEYS | schema.SYSTEM_KEYS)
    assert _ts_keys(ts) == declared


def test_fixture_is_valid_and_flagged_synthetic():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert schema.validate_report(data) == []
    assert data["synthetic_fixture"] is True and data["assessment"]["simulees"] == 0


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.pop("git_sha"), "missing ['git_sha']"),
    (lambda d: d.update(extra=1), "unexpected ['extra']"),
    (lambda d: d["assessment"].update(exact_acc=1.2), "outside [0, 1]"),
    (lambda d: d["assessment"].update(qwk=float("nan")), "finite number"),
    (lambda d: d["assessment"]["confusion"].pop(), "4x4"),
    (lambda d: d["assessment"]["tif"]["info"].pop(), "equal-length"),
    (lambda d: d["assessment"]["leak_attack"][0].pop("static_dtheta"), "missing ['static_dtheta']"),
    (lambda d: d["matching"]["systems"][0].update(ndcg10=-0.1), "in [0, 1]"),
    (lambda d: d.update(synthetic_fixture="yes"), "boolean"),
    (lambda d: d["assessment"].update(generator_errors=1.5), "integer"),
])
def test_invalid_reports_are_rejected(mutate, message):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = copy.deepcopy(data)
    mutate(bad)
    errs = schema.validate_report(bad)
    assert any(message in e for e in errs), errs
