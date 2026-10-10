"""ML-2: content files load, are consistent with each other and with the registry, and drive blueprints."""
from __future__ import annotations

import shutil

import pytest
import yaml
from assessment.engine.blueprint import blueprint_for
from assessment.engine.content import CONTENT_DIR, ContentError, load_content
from assessment.families import verify as harness
from assessment.families.base import GRADES, SPECS
from assessment.families.registry import all_families

C = load_content()


def test_grade_scale_resolves_ml_f2_to_the_documented_cuts():
    assert [g.id for g in C.grades] == list(GRADES)
    assert [g.theta_cut for g in C.grades] == [-2.0, -1.0, 0.0, 1.0]     # intern floor + −1/0/+1
    assert C.band_cuts == (-1.0, 0.0, 1.0)
    assert [g.rating_cut for g in C.grades] == [600, 800, 1000, 1200]   # 1000 + 200θ
    assert [g.start_theta for g in C.grades] == [-1.5, -1.0, 0.0, 1.0]
    assert all(g.descriptor_ru and g.name_ru for g in C.grades)


def test_topics_reference_known_skills_and_specs():
    skills = harness._skills_catalog()
    for t in C.topics.values():
        assert set(t.specs) <= set(SPECS) and t.skills
        assert set(t.skills) <= skills, (t.id, set(t.skills) - skills)


def test_blueprints_cover_every_topic_of_their_spec_and_sum_to_one():
    for spec in SPECS:
        bp = C.blueprints[spec]
        assert set(bp) == set(C.topics_for(spec))
        assert sum(bp.values()) == pytest.approx(1.0, abs=1e-12)


def test_every_family_topic_exists_and_serves_its_specs():
    for fam in all_families().values():
        topic = C.topics[fam.meta.topic]
        assert set(fam.meta.specs) <= set(topic.specs)


# ── malformed files are refused ────────────────────────────────────────────

def _copy(tmp_path):
    for name in ("grades.yaml", "specializations.yaml", "blueprints.yaml"):
        shutil.copy(CONTENT_DIR / name, tmp_path / name)
    return tmp_path


def _move_weight(bp, src, dst):
    bp[dst] += bp.pop(src)                          # the sum stays 1, the topic disappears


def _edit(path, fn):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize("fname, mutate, message", [
    ("blueprints.yaml", lambda d: d["blueprints"]["backend"].update({"sql.joins": 0.2}), "sum to"),
    ("blueprints.yaml", lambda d: _move_weight(d["blueprints"]["backend"], "sql.joins", "sql.aggregation"),
     "without a weight"),
    ("blueprints.yaml", lambda d: d["blueprints"]["frontend"].update({"sql.joins": 0.0}), "not a frontend topic"),
    ("grades.yaml", lambda d: d["grades"].reverse(), "in order"),
    ("grades.yaml", lambda d: d["grades"][2].update({"rating_cut": 1050}), "rating_cut"),
    ("grades.yaml", lambda d: d["grades"][2].update({"theta_cut": -1.5, "rating_cut": 700}), "increase"),
    ("specializations.yaml", lambda d: d["topics"].append(dict(d["topics"][0])), "duplicate topic"),
    ("specializations.yaml", lambda d: d["topics"][0].update({"specs": ["devops"]}), "bad specs"),
])
def test_malformed_content_is_refused(tmp_path, fname, mutate, message):
    root = _copy(tmp_path)
    _edit(root / fname, mutate)
    with pytest.raises(ContentError, match=message):
        load_content(str(root))


def test_missing_file_is_refused(tmp_path):
    root = _copy(tmp_path)
    (root / "grades.yaml").unlink()
    with pytest.raises(ContentError, match="missing"):
        load_content(str(root))


# ── blueprint_for: hand-computed goldens ───────────────────────────────────

def test_blueprint_for_python_asyncio_backend_by_hand():
    # python.core 0.12 (python: 1 hit) -> 0.24; backend.concurrency 0.08 (asyncio, python: 2 hits)
    # -> 0.24; algorithms.code_reading lists only `algorithms`, so no hit. Total 0.48 -> 0.5 each,
    # tie broken by topic id.
    assert blueprint_for("backend", ["python", "asyncio"]) == [("backend.concurrency", 0.5), ("python.core", 0.5)]
    # algorithms + python + asyncio: code_reading 0.10·2 = 0.20, complexity 0.10·2, data_structures
    # 0.10·2, python.core 0.24, concurrency 0.24; total 1.08 -> 0.2222 (x2), 0.1852 (x3); Σ = 1.0
    bp = blueprint_for("backend", ["algorithms", "python", "asyncio"])
    assert bp == [("backend.concurrency", 0.2222), ("python.core", 0.2222), ("algorithms.code_reading", 0.1852),
                  ("algorithms.complexity", 0.1852), ("algorithms.data_structures", 0.1852)]


def test_blueprint_for_sql_on_ml_data_by_hand():
    # ml_data: sql.aggregation 0.10 -> 0.20, sql.joins 0.05 -> 0.10; total 0.30
    assert blueprint_for("ml_data", ["SQL "]) == [("sql.aggregation", 0.6667), ("sql.joins", 0.3333)]


def test_blueprint_for_without_hits_is_the_category_blueprint():
    bp = blueprint_for("frontend", ["no_such_skill"])
    assert dict(bp) == pytest.approx(C.blueprints["frontend"])
    assert blueprint_for("frontend", []) == bp
    assert sum(w for _, w in bp) == pytest.approx(1.0, abs=1e-9)
    with pytest.raises(ValueError):
        blueprint_for("devops", ["sql"])


def test_blueprint_feeds_the_jd_parser():
    from llm_gateway.fake import FakeLlm
    from llm_gateway.jd import parse_jd
    res = parse_jd("Backend-разработчик Python. Обязательно: Python, PostgreSQL, SQL. "
                   "Зарплата 250 000 – 320 000 ₽ gross.", gateway=FakeLlm())
    assert res.draft.get("specialization") == "backend"
    assert res.blueprint and abs(sum(b["weight"] for b in res.blueprint) - 1) < 1e-9
    assert {b["topic"] for b in res.blueprint} <= set(C.topics_for("backend"))
    assert res.fallback_reason == "provider_fake"                 # no "+blueprint" failure marker


def test_item_bank_doc_is_current():
    """docs/ml/item-bank.md is generated from the registry; regenerate with
    `cd apps && python -m assessment.families.catalog` after changing families or content."""
    from assessment.families.catalog import OUT, render
    assert OUT.read_text(encoding="utf-8") == render()
