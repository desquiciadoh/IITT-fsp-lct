"""ML-7: the synthetic world is deterministic, schema-valid, consistent with the formulas, and keeps
the hidden truth out of the public files."""
from __future__ import annotations

import json

import pytest
from assessment.families import verify as harness

from validation import synth

WORLD = synth.build_world(seed=7, n_candidates=160, n_positions=20)
SKILLS = harness._skills_catalog()
GRADES = ("intern", "junior", "middle", "senior")


def test_same_seed_same_world_and_a_different_seed_differs(tmp_path):
    a = synth.write_world(synth.build_world(seed=7, n_candidates=160, n_positions=20), tmp_path / "a", tmp_path / "ta.jsonl")
    b = synth.write_world(synth.build_world(seed=7, n_candidates=160, n_positions=20), tmp_path / "b", tmp_path / "tb.jsonl")
    c = synth.write_world(synth.build_world(seed=8, n_candidates=160, n_positions=20), tmp_path / "c", tmp_path / "tc.jsonl")
    assert a == b
    assert a["sha256"]["candidates"] != c["sha256"]["candidates"]


def test_public_rows_never_carry_the_hidden_truth(tmp_path):
    synth.write_world(WORLD, tmp_path / "seed", tmp_path / "truth.jsonl")
    public = "".join((tmp_path / "seed" / f"{name}.jsonl").read_text(encoding="utf-8") for name in synth.FILES)
    for field in ("true_grade", "proficiency", "inflation", '"tested"'):
        assert field not in public
    truth = [json.loads(x) for x in (tmp_path / "truth.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {t["public_id"] for t in truth} == {c["public_id"] for c in WORLD.candidates}


def test_candidate_rows_are_valid():
    for c in WORLD.candidates:
        assert c["public_id"].startswith("C-") and c["email"].endswith("@example.com")
        assert c["specialization"] in ("backend", "frontend", "ml_data") and c["claimed_grade"] in GRADES
        assert {s["skill_id"] for s in c["skills"]} <= SKILLS
        assert {s["source"] for s in c["skills"]} <= {"declared", "test", "fsp"}
        assert 0 < c["salary_min"] <= c["salary_max"] and c["salary_type"] in ("gross", "net")   # invariant 5
        assert set(c["work_formats"]) <= {"remote", "hybrid", "office"} and c["work_formats"]
        assert c["cv_text"] and "@" not in c["cv_text"]


def test_leagues_use_the_production_formulas():
    from matching.engine.strength import percentile_of
    by_league: dict[tuple, list] = {}
    for lg in WORLD.leagues:
        by_league.setdefault((lg["specialization"], lg["grade"]), []).append(lg)
        assert lg["status"] in ("confirmed", "unconfirmed")
        assert 0 <= lg["strength"] <= 100 and 0 <= lg["fsp_boost"] <= 15
        assert lg["rating"] == round(1000 + 200 * lg["theta"]) or abs(lg["rating"] - (1000 + 200 * lg["theta"])) <= 1
    for members in by_league.values():
        thetas = [m["theta"] for m in members]
        for m in members:
            assert m["percentile"] == pytest.approx(percentile_of(m["theta"], thetas), abs=0.01)


def test_fsp_rows_follow_the_registry_contract():
    tiers = {"winner", "prize_winner", "finalist", "participant"}
    for f in WORLD.fsp:
        assert set(f) >= {"participant_id", "sports_rank", "results", "issued_at", "signature"}
        assert f["participant_id"].startswith("FSP-")
        for r in f["results"]:
            assert set(r) >= {"event_id", "event_name", "date", "discipline", "stage", "format", "placement",
                              "placement_tier", "participants_total"}
            assert r["placement_tier"] in tiers and r["discipline"] in synth.DISCIPLINES
            assert r["placement"] <= r["participants_total"]
    share = len(WORLD.fsp) / len(WORLD.candidates)
    assert 0.2 <= share <= 0.5                                       # ~35 % target, small sample


def test_fsp_correlates_with_ability():
    world = synth.build_world(seed=11, n_candidates=600, n_positions=5)
    truth = {t["public_id"]: t["theta"] for t in world.truth}
    with_fsp = [truth[f["public_id"]] for f in world.fsp]
    without = [truth[p] for p in truth if p not in {f["public_id"] for f in world.fsp}]
    assert sum(with_fsp) / len(with_fsp) > sum(without) / len(without) + 0.3


def test_positions_are_valid_and_reference_known_skills():
    companies = {c["company_id"] for c in WORLD.companies}
    assert len(WORLD.companies) == 12
    for p in WORLD.positions:
        assert p["company_id"] in companies
        assert set(p["must_skills"]) <= SKILLS and set(p["nice_skills"]) <= SKILLS and p["must_skills"]
        assert not set(p["must_skills"]) & set(p["nice_skills"])
        assert 0 < p["salary_min"] <= p["salary_max"] and p["salary_type"] in ("gross", "net")
        assert set(p["grades"]) <= set(GRADES)


def test_heroes_are_injected_with_their_story():
    """The scripted parts of the personas hold in the shipped world (seed 2026): who has FSP
    history, who is closed to offers, and that Dmitry's inflated senior claim is not confirmed."""
    world = synth.build_world(seed=2026, n_candidates=len(synth.HEROES), n_positions=1)
    by_hero = {c["hero"]: c for c in world.candidates if c["hero"]}
    assert set(by_hero) == {h["key"] for h in synth.HEROES}
    leagues = {lg["public_id"]: lg for lg in world.leagues}
    fsp = {f["public_id"] for f in world.fsp}
    assert by_hero["anna"]["public_id"] in fsp and by_hero["alex"]["public_id"] not in fsp
    assert leagues[by_hero["dmitry"]["public_id"]]["status"] == "unconfirmed"
    assert by_hero["olga"]["open_to_offers"] is False


def test_hero_grade_stories_hold_on_most_sessions():
    """Session outcomes are honest draws, so one seed can be unlucky (a θ = 2.0 senior is confirmed in
    about 95 % of sessions). The stories must hold on >= 85 % of 60 independent sessions each; the
    shipped seed is not re-drawn to make a story come true."""
    from assessment.engine.cat import IrtCatEngine
    from assessment.families.registry import active_metas
    from validation.simulate import perturbed_params, run_session

    engine = IrtCatEngine()
    pools = {spec: active_metas(spec) for spec in ("backend", "frontend", "ml_data")}
    metas = {m.id: m for pool in pools.values() for m in pool}
    true_params = perturbed_params(list(metas.values()), 2026)
    for hero in synth.HEROES:
        outcomes = [run_session(engine, pools[hero["spec"]], true_params, hero["spec"], hero["claim"], hero["theta"],
                                f"hero|{hero['key']}|{k}").result.decision for k in range(60)]
        want = "unconfirmed" if hero["key"] == "dmitry" else "confirmed"
        assert outcomes.count(want) / len(outcomes) >= 0.85, (hero["key"], outcomes.count(want))


def test_declared_skills_inflate_and_omit_relative_to_truth():
    truth = {t["public_id"]: t for t in WORLD.truth}
    inflated = omitted = 0
    for c in WORLD.candidates:
        prof = truth[c["public_id"]]["proficiency"]
        declared = {s["skill_id"] for s in c["skills"] if s["source"] == "declared"}
        inflated += len(declared - {k for k, v in prof.items() if v >= 0.45})
        omitted += len({k for k, v in prof.items() if v >= 0.45} - declared)
    assert inflated > 0 and omitted > 0


def test_seed_readme_documents_every_file():
    text = (synth.ROOT / "seed_data" / "README.md").read_text(encoding="utf-8")
    for name in (*synth.FILES, "manifest"):
        assert f"{name}.json" in text
