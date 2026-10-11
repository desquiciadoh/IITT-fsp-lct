"""ML-13 (retirement, promotion blueprint) and ML-14 (pilot analysis) behaviour."""
from __future__ import annotations

import random

import pytest
from assessment.engine.cat import IrtCatEngine
from assessment.engine.content import load_content
from assessment.families.registry import RETIRED, active_metas, all_families

from validation.pilot import PilotDataError, run_pilot_analysis, spearman_rho

SPECS = ("backend", "frontend", "ml_data")


def test_retired_families_stay_registered_but_are_never_active():
    fams = all_families()
    for fid in RETIRED:
        assert fid in fams                                 # pending sessions can still finish
        for spec in SPECS:
            assert fid not in {m.id for m in active_metas(spec)}


def test_every_blueprint_topic_keeps_an_active_family_after_retirement():
    content = load_content()
    for spec in SPECS:
        topics = {m.topic for m in active_metas(spec)}
        missing = sorted(t for t in content.blueprints[spec] if t not in topics)
        assert not missing, f"{spec}: no active family for {missing}"


def test_promotion_starts_at_the_next_grade_and_prefers_hard_items():
    engine, content = IrtCatEngine(), load_content()
    pool = active_metas("backend")
    cut = content.grade("middle").theta_cut + content.promotion_min_b_offset
    for seed in range(20):
        promo = engine.start("backend", "junior", "full", "promotion", pool, set())
        initial = engine.start("backend", "junior", "full", "initial", pool, set())
        m_promo = engine.next_family(promo, pool, random.Random(seed))
        m_init = engine.next_family(initial, pool, random.Random(seed))
        assert m_promo.b >= cut
        assert m_init is not None
    # a senior has no next grade: promotion behaves like an initial test
    s = engine.start("backend", "senior", "full", "promotion", pool, set())
    assert engine.next_family(s, pool, random.Random(0)) is not None


def test_pilot_reports_no_data_without_files(tmp_path):
    out = run_pilot_analysis(tmp_path)
    assert out["assessments"] == {"status": "no_data"}
    assert out["annotations"]["status"] == "no_data"


def _write(path, header, rows):
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def test_pilot_metrics_on_a_synthetic_fixture(tmp_path):
    _write(tmp_path / "assessments.csv", "person,known_grade,attempt,grade", [
        "p1,junior,1,junior", "p2,middle,1,senior", "p3,senior,1,senior", "p4,intern,1,junior",
        "p1,junior,2,junior", "p2,middle,2,middle",
    ])
    _write(tmp_path / "annotations.csv", "pair_id,annotator_a,annotator_b,oracle", [
        "a,0,0,0.1", "b,1,2,0.4", "c,3,3,0.9", "d,2,2,0.7",
    ])
    out = run_pilot_analysis(tmp_path)
    a = out["assessments"]
    assert (a["n"], a["exact"], a["adjacent"]) == (4, 0.5, 1.0)
    assert a["retest"] == {"status": "ok", "n": 2, "same_grade": 0.5, "qwk": pytest.approx(a["retest"]["qwk"])}
    assert out["annotations"]["spearman_oracle_human"] == 1.0      # oracle order = mean human order
    assert out["annotations"]["n"] == 4


def test_spearman_handles_ties_golden():
    # ranks x: 0, 1.5, 1.5, 3; y: 0, 1, 2, 3 -> r = 0.9487
    assert spearman_rho([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.948683, abs=1e-6)


@pytest.mark.parametrize("row", ["p1,lead,1,junior", "p1,junior,3,junior", "p1,junior,1,junior\np1,junior,1,middle"])
def test_malformed_pilot_rows_raise(tmp_path, row):
    _write(tmp_path / "assessments.csv", "person,known_grade,attempt,grade", [row])
    with pytest.raises(PilotDataError):
        run_pilot_analysis(tmp_path)


def test_out_of_range_annotation_label_raises(tmp_path):
    _write(tmp_path / "annotations.csv", "pair_id,annotator_a,annotator_b,oracle", ["a,4,0,0.1"])
    with pytest.raises(PilotDataError):
        run_pilot_analysis(tmp_path)
