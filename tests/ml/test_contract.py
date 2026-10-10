"""ML-0: the published contract (ML.md §3) has its final shapes, and the engine packages stay pure."""
from __future__ import annotations

import ast
import dataclasses
import datetime
import hashlib
import hmac
import json
import random
from pathlib import Path

import pytest
from assessment.engine.blueprint import blueprint_for
from assessment.engine.cat import CatState, IrtCatEngine, band_of, item_level
from assessment.families import base as fbase
from assessment.families.base import FamilyMeta, Instance, fingerprint_of
from assessment.families.registry import active_metas, all_families, make_rng
from matching.engine import types as mtypes
from matching.engine.score import passes_hard_filters, preset, score_pool
from matching.engine.strength import percentile_of, percentiles

ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIRS = [ROOT / "apps/assessment/families", ROOT / "apps/assessment/engine",
               ROOT / "apps/matching/engine"]


def _meta(fid: str, b: float = 0.0, topic: str = "t") -> FamilyMeta:
    return FamilyMeta(id=fid, version=1, specs=("backend",), topic=topic, skills=("sql",),
                      format="concept_mcq", a=1.2, b=b, c=0.25, time_limit_s=90)


# ── purity ─────────────────────────────────────────────────────────────────

ENGINE_FILES = [p for d in ENGINE_DIRS for p in sorted(d.rglob("*.py"))]
BANNED = ("django", "rest_framework", "core", "profiles", "identity", "outreach", "fsp_sync", "llm_gateway")
DJANGO_MODULES = ("models", "views", "serializers", "services", "selectors", "admin", "tasks", "urls")


def _imports(path: Path) -> list[str]:
    """Absolute module names imported by a file; relative imports are resolved against its package."""
    pkg = list(path.relative_to(ROOT / "apps").with_suffix("").parts[:-1])
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = pkg[: len(pkg) - node.level + 1] if node.level else []
            mod = ".".join([*base, *([node.module] if node.module else [])])
            names += [f"{mod}.{a.name}" if not node.module or node.level else mod for a in node.names]
    return names


@pytest.mark.parametrize("path", ENGINE_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_engine_modules_import_no_django_orm_or_core(path):
    bad = [m for m in _imports(path)
           if any(m == b or m.startswith(b + ".") for b in BANNED)
           or any(part in DJANGO_MODULES for part in m.split(".")[1:])]
    assert bad == []


@pytest.mark.parametrize("path", ENGINE_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_engine_modules_use_no_global_rng(path):
    """Only random.Random(...) instances; never random.<fn>() or np.random.<fn>() (invariant 6)."""
    bad = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = ast.unparse(node.func.value)
            if owner == "random" and node.func.attr != "Random":
                bad.append(f"{node.lineno}: random.{node.func.attr}")
            if owner in ("np.random", "numpy.random") and node.func.attr != "default_rng":
                bad.append(f"{node.lineno}: {owner}.{node.func.attr}")
    assert bad == []


def test_purity_scan_catches_relative_model_import(tmp_path):
    fake = ROOT / "apps/assessment/engine/_probe_tmp.py"
    fake.write_text("from ..models import AssessmentSession\nfrom ... import core\n", encoding="utf-8")
    try:
        assert "assessment.models.AssessmentSession" in _imports(fake)
    finally:
        fake.unlink()


def test_string_constants_match_core_enums():
    from core import enums
    assert fbase.SPECS == tuple(enums.Specialization.values)
    assert fbase.GRADES == tuple(enums.Grade.values)
    assert fbase.ITEM_FORMATS == tuple(enums.ItemFormat.values)
    assert mtypes.SOURCES == tuple(enums.EvidenceSource.values)
    assert mtypes.TIERS == tuple(enums.PlacementTier.values)
    assert mtypes.RANKS == tuple(enums.SportsRank.values)
    assert mtypes.SALARY_TYPES == tuple(enums.SalaryType.values)
    assert mtypes.LEAGUE_STATUSES == tuple(enums.LeagueStatus.values)
    from assessment.engine import cat, legacy
    assert cat.MODES == tuple(enums.AssessmentMode.values)
    assert cat.KINDS == tuple(enums.AssessmentKind.values)
    assert [legacy.Grade.INTERN, legacy.Grade.JUNIOR, legacy.Grade.MIDDLE, legacy.Grade.SENIOR] == \
        list(enums.Grade.values)
    assert [legacy.GradeDecision.CONFIRMED, legacy.GradeDecision.UNCONFIRMED] == \
        list(enums.GradeDecision.values)


# ── families contract ──────────────────────────────────────────────────────

def test_make_rng_is_hmac_sha256_of_session_purpose_n():
    secret, sid = b"s3cret", "2b0c9f7e-1111-4222-8333-444455556666"
    digest = hmac.new(secret, f"{sid}|be.sql.x|3".encode(), hashlib.sha256).digest()
    expected = random.Random(int.from_bytes(digest, "big"))
    got = make_rng(secret, sid, "be.sql.x", 3)
    assert [got.random() for _ in range(5)] == [expected.random() for _ in range(5)]
    # pinned literal: catches any change of message format or encoding
    assert make_rng(b"k", "sess-1", "be.sql.x", 3).random() == 0.45017091589546465
    assert make_rng("k", "sess-1", "be.sql.x", 3).random() == 0.45017091589546465


def test_make_rng_refuses_an_empty_secret():
    for empty in (b"", ""):
        with pytest.raises(ValueError):
            make_rng(empty, "s", "select", 1)


def test_make_rng_streams_differ_by_every_input():
    def first(*args):
        return make_rng(*args).getrandbits(64)
    ref = first(b"k", "s", "p", 1)
    assert ref == first(b"k", "s", "p", 1)
    assert len({ref, first(b"K", "s", "p", 1), first(b"k", "S", "p", 1),
                first(b"k", "s", "P", 1), first(b"k", "s", "p", 2)}) == 5


def test_view_never_carries_key_or_fingerprint():
    inst = Instance(stem_md="Сколько строк?", input="choice", key="o1234abcd",
                    fingerprint="f" * 64, code={"lang": "sql", "text": "SELECT 1"},
                    options=[{"id": "o1234abcd", "text_md": "1", "_correct": True},
                             {"id": "o9999ffff", "text_md": "2"}])
    inst.code["expected"] = "debug leftovers must not reach the client"
    v = inst.view()
    assert set(v) == {"stem_md", "input", "code", "options"}
    assert set(v["code"]) == {"lang", "text"}
    assert all(set(o) == {"id", "text_md"} for o in v["options"])
    assert "f" * 64 not in json.dumps(v)


def test_fingerprint_is_canonical_json_of_params():
    assert fingerprint_of({"b": 1, "a": [1, 2]}) == fingerprint_of({"a": [1, 2], "b": 1})
    assert fingerprint_of({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()
    assert fingerprint_of({"a": 1}) != fingerprint_of({"a": 2})


def test_registry_shapes():
    fams = all_families()
    assert list(fams) == sorted(fams)
    for spec in fbase.SPECS:
        metas = active_metas(spec)
        assert all(spec in m.specs for m in metas)
    with pytest.raises(ValueError):
        active_metas("devops")


# ── CAT contract ───────────────────────────────────────────────────────────

def test_band_and_item_level_use_cuts_minus1_0_1():
    assert [band_of(x) for x in (-1.01, -1.0, -0.01, 0.0, 0.99, 1.0)] == \
        ["intern", "junior", "junior", "middle", "middle", "senior"]
    assert item_level(_meta("x", b=0.4)) == "middle"


def test_cat_state_round_trips_through_json():
    st = CatState(spec="frontend", claimed="junior", mode="express", kind="fallback",
                  administered=[{"family_id": "x", "seq": 1, "a": 1.3, "b": -0.25, "c": 0.25,
                                 "topic": "t", "correct": True, "late": False}],
                  theta=0.123456789, se=0.4321, min_items=8, max_items=8, seen=["a", "b"],
                  blueprint=[("sql.aggregation", 0.6), ("python.core", 0.4)], stop_reason="ci")
    assert CatState.from_json(json.loads(json.dumps(st.to_json()))) == st
    assert st.to_json()["v"] == 1


def test_cat_state_reads_v1_dicts_without_optional_fields_and_refuses_newer():
    old = {"spec": "backend", "claimed": "middle", "mode": "full", "kind": "initial", "administered": [],
           "theta": 0.0, "se": 1.0, "min_items": 10, "max_items": 20}
    st = CatState.from_json(old)
    assert st.seen == [] and st.blueprint is None
    with pytest.raises(ValueError):
        CatState.from_json({**old, "v": 99})


def test_start_keeps_a_screening_blueprint():
    st = IrtCatEngine().start("backend", "middle", "full", "screening", [_meta("a")], set(),
                               blueprint=[("sql.aggregation", 1.0)])
    assert CatState.from_json(st.to_json()).blueprint == [("sql.aggregation", 1.0)]


def test_blueprint_shape():
    bp = blueprint_for("backend", ["sql"])
    assert all(isinstance(t, str) and isinstance(w, float) for t, w in bp)
    assert bp == [] or sum(w for _, w in bp) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        blueprint_for("devops", [])


# ── matching contract ──────────────────────────────────────────────────────

NOW = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.UTC)


def _cand(pid: str, **kw) -> mtypes.CandidateCtx:
    base = mtypes.CandidateCtx(
        public_id=pid, specialization="backend", league_grade="middle", league_status="confirmed",
        theta=0.5, se=0.3, rating=1100, percentile=50.0, strength=60.0,
        skills=(mtypes.SkillEvidence("sql", "test", 1.0),), topic_levels={}, fsp_rank=None,
        fsp_results=(), salary_min=200_000, salary_max=250_000, salary_type="gross",
        work_formats=("remote",), city="Москва", timezone="Europe/Moscow", last_active_at=NOW)
    return dataclasses.replace(base, **kw)


NEED = mtypes.NeedCtx(position_id="p1", specialization="backend", grades=("middle",), allow_adjacent=False,
                      must_skills=("sql", "python"), nice_skills=("docker",), work_formats=("remote",),
                      location="Москва", salary_min=200_000, salary_max=300_000, salary_type="gross")


def test_score_pool_shapes_sum_and_tiebreak():
    pool = [_cand("C-B"), _cand("C-A"), _cand("C-C", skills=())]
    out = score_pool(NEED, pool, preset("balanced"), NOW)
    assert [s.public_id for s in out] == ["C-A", "C-B", "C-C"]          # equal scores -> by public_id
    for s in out:
        assert [c.key for c in s.components] == list(mtypes.COMPONENT_KEYS)
        assert s.score == pytest.approx(sum(c.contribution for c in s.components), abs=1e-9)
        assert 0 <= s.score <= 100 and len(s.reasons) >= len(s.components)
        assert all(r.text for r in s.reasons)
    assert out[-1].gaps == ("SQL", "Python")             # display names of missing must-haves


@pytest.mark.parametrize("name", ["balanced", "skills", "budget"])
def test_every_documented_preset_resolves_and_keeps_scores_in_range(name):
    out = score_pool(NEED, [_cand("C-1")], preset(name), NOW)
    assert sum(c.weight for c in out[0].components) == pytest.approx(100.0)
    assert 0 <= out[0].score <= 100


def test_slider_weights_are_rescaled_to_100():
    out = score_pool(NEED, [_cand("C-1")], mtypes.Weights(70, 40, 30, 30, 20, 10), NOW)
    assert [c.weight for c in out[0].components] == pytest.approx([35, 20, 15, 15, 10, 5])
    with pytest.raises(ValueError):
        score_pool(NEED, [_cand("C-1")], mtypes.Weights(0, 0, 0, 0, 0, 0), NOW)


def test_hard_filters_reference():
    assert passes_hard_filters(NEED, _cand("C-1"))
    assert not passes_hard_filters(NEED, _cand("C-1", specialization="frontend"))
    assert not passes_hard_filters(NEED, _cand("C-1", league_grade="senior"))
    adj = dataclasses.replace(NEED, allow_adjacent=True)
    assert passes_hard_filters(adj, _cand("C-1", league_grade="senior"))
    assert not passes_hard_filters(adj, _cand("C-1", league_grade="intern"))
    assert not passes_hard_filters(NEED, _cand("C-1", work_formats=("office",)))


def test_percentiles_mid_rank_by_hand():
    assert percentiles([1.0, 2.0, 2.0, 3.0]) == [12.5, 50.0, 50.0, 87.5]
    assert percentiles([0.3]) == [50.0]
    assert percentiles([]) == []
    assert percentile_of(3.0, [1.0, 2.0, 2.0, 3.0]) == 87.5
    with pytest.raises(ValueError):
        percentiles([float("nan"), 1.0, 0.0])
