"""ML-4: NDFL conversion, FSP boost, Strength, match features and hand-ranked pools.

Every golden below is derived by hand in the comment next to it.
"""
from __future__ import annotations

import dataclasses
import datetime
import math
import re

import pytest
from matching.engine import features as F
from matching.engine.salary import annual_tax, to_gross, to_net
from matching.engine.score import preset, score_candidate, score_pool
from matching.engine.strength import activity, freshness, fsp_boost, placement_sum, strength
from matching.engine.types import (
    COMPONENT_KEYS,
    CandidateCtx,
    FspResultCtx,
    NeedCtx,
    SkillEvidence,
    Weights,
)

NOW = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.UTC)
CYRILLIC = re.compile("[а-яё]", re.IGNORECASE)


# ── NDFL (п. 1 ст. 224 НК РФ, 2025+) ───────────────────────────────────────

def test_annual_tax_matches_fns_example_and_bracket_edges():
    # FNS: 3 M ₽ -> 13 % of 2.4 M (312 000) + 15 % of 0.6 M (90 000) = 402 000
    assert annual_tax(3_000_000) == pytest.approx(402_000)
    assert annual_tax(2_400_000) == pytest.approx(312_000)
    assert annual_tax(5_000_000) == pytest.approx(702_000)          # 312 000 + 2.6 M · 15 %
    assert annual_tax(20_000_000) == pytest.approx(3_402_000)       # + 15 M · 18 %
    assert annual_tax(50_000_000) == pytest.approx(9_402_000)       # + 30 M · 20 %
    assert annual_tax(60_000_000) == pytest.approx(11_602_000)      # + 10 M · 22 %
    assert annual_tax(0) == 0


def test_monthly_gross_net_by_hand():
    # 250 000 gross/month = 3 M/year -> tax 402 000 -> net 2 598 000/12 = 216 500
    assert to_net(250_000, "gross") == 216_500
    assert to_gross(216_500, "net") == 250_000
    # 200 000 gross = 2.4 M: exactly at the first threshold, net 174 000
    assert to_net(200_000, "gross") == 174_000 and to_gross(174_000, "net") == 200_000
    # 300 000 net = 3.6 M/yr net: 2.4 M + (3.6 M − 2.088 M)/0.85 = 4 178 823.5 gross -> 348 235/month
    assert to_gross(300_000, "net") == 348_235
    assert to_gross(123, "gross") == 123 and to_net(123, "net") == 123
    with pytest.raises(ValueError):
        to_gross(100, "cash")


@pytest.mark.parametrize("gross", [50_000, 199_999, 200_001, 416_666, 416_667, 1_666_667, 4_166_667, 9_000_000])
def test_gross_net_round_trip_across_brackets(gross):
    assert abs(to_gross(to_net(gross, "gross"), "net") - gross) <= 1


# ── FSP boost and Strength ─────────────────────────────────────────────────

def _r(tier, day=1, disc="algorithmic", n=100, team=None):
    return FspResultCtx(tier, datetime.date(2025, 3, day), disc, n, team)


def test_fsp_boost_by_hand():
    assert fsp_boost(None, [], NOW) == 0.0                                      # no FSP -> 0
    # one win: R = 1 -> 12 (1 − e^−0.5) = 4.72163
    assert fsp_boost(None, [_r("winner")], NOW) == pytest.approx(12 * (1 - math.exp(-0.5)))
    assert fsp_boost("kms", [_r("winner")], NOW) == pytest.approx(12 * (1 - math.exp(-0.5)) + 2)
    # five participations: 0.75 capped at 0.6 -> 12 (1 − e^−0.3) = 3.11018
    five = [_r("participant", d) for d in range(1, 6)]
    assert placement_sum(five, NOW) == pytest.approx(0.6)
    assert fsp_boost(None, five, NOW) == pytest.approx(12 * (1 - math.exp(-0.3)))
    # prize-winner + finalist + 2 participations: R = 0.7 + 0.4 + 0.3 = 1.4
    mix = [_r("prize_winner", 1), _r("finalist", 2), _r("participant", 3), _r("participant", 4)]
    assert fsp_boost("cat2", mix, NOW) == pytest.approx(12 * (1 - math.exp(-0.7)))
    assert fsp_boost("cat1", [], NOW) == 1.0 and fsp_boost("ms", [], NOW) == 3.0


def test_fsp_boost_bounded_idempotent_and_ignores_future():
    many = [_r("winner", d, disc) for d in range(1, 28) for disc in ("algorithmic", "product")]
    assert fsp_boost("ms", many, NOW) <= 15.0 and fsp_boost("ms", many, NOW) > 14.9
    once = [_r("winner"), _r("finalist", 2)]
    assert fsp_boost("kms", once, NOW) == fsp_boost("kms", once * 3, NOW) == fsp_boost("kms", once[::-1], NOW)
    future = FspResultCtx("winner", datetime.date(2027, 1, 1), "product", 10, None)
    assert fsp_boost(None, [future], NOW) == 0.0
    with pytest.raises(ValueError):
        fsp_boost(None, [FspResultCtx("champion", datetime.date(2025, 1, 1), "uas", 1, None)], NOW)


def test_disciplines_weigh_the_same():
    a = fsp_boost(None, [_r("winner", disc="algorithmic")], NOW)
    b = fsp_boost(None, [_r("winner", disc="robotics")], NOW)
    assert a == b


def test_activity_and_freshness_by_hand():
    assert activity([], NOW) == 0.0
    # one task today: S = 1 -> 1 − e^−1; one 90 days ago: S = 0.5
    assert activity([NOW.date()], NOW) == pytest.approx(1 - math.exp(-1))
    assert activity([NOW.date() - datetime.timedelta(days=90)], NOW) == pytest.approx(1 - math.exp(-0.5))
    assert freshness(NOW, NOW) == 1.0 and freshness(None, NOW) == 0.0
    assert freshness(NOW - datetime.timedelta(days=30), NOW) == pytest.approx(0.5)


def _cand(pid="C-1", **kw) -> CandidateCtx:
    base = CandidateCtx(
        public_id=pid, specialization="backend", league_grade="middle", league_status="confirmed",
        theta=0.4, se=0.3, rating=1080, percentile=60.0, strength=70.0, skills=(), topic_levels={},
        fsp_rank=None, fsp_results=(), salary_min=280_000, salary_max=300_000, salary_type="gross",
        work_formats=("remote",), city="Москва", timezone="Europe/Moscow", last_active_at=NOW)
    return dataclasses.replace(base, **kw)


def test_strength_by_hand():
    # league θ = [−0.5, 0.0, 0.4, 0.9] -> θ 0.4 percentile (2 + 0.5)/4 = 62.5
    # base = 0.75·62.5 + 0.15·0 + 0.10·100·1 = 56.875; total = 0.85·56.875 + boost
    league = [-0.5, 0.0, 0.4, 0.9]
    plain = strength(_cand(), league, NOW)
    assert plain.percentile == 62.5 and plain.base == pytest.approx(56.875)
    assert plain.fsp_boost == 0.0 and plain.total == pytest.approx(0.85 * 56.875)
    fsp = strength(_cand(fsp_rank="kms", fsp_results=(_r("winner"),)), league, NOW)
    assert fsp.total == pytest.approx(0.85 * 56.875 + 12 * (1 - math.exp(-0.5)) + 2)
    top = strength(_cand(theta=5.0, fsp_rank="ms", fsp_results=tuple(_r("winner", d) for d in range(1, 20)),
                         microtask_dates=(NOW.date(),) * 3), [5.0], NOW)
    assert top.total <= 100.0
    assert strength(_cand(theta=None), league, NOW).percentile == 0.0


def test_fsp_changes_strength_never_grade():
    c = _cand(fsp_rank="ms", fsp_results=(_r("winner"),))
    s = strength(c, [0.4], NOW)
    assert s.fsp_boost > 0 and c.league_grade == "middle" and c.league_status == "confirmed"


# ── features ───────────────────────────────────────────────────────────────

NEED = NeedCtx(position_id="P-1", specialization="backend", grades=("middle",), allow_adjacent=True,
               must_skills=("sql", "python"), nice_skills=("docker",), work_formats=("remote",),
               location="Москва", salary_min=250_000, salary_max=320_000, salary_type="gross")


def test_skill_fit_by_hand():
    # skills.yaml (AI): python–sql and docker–kubernetes are related
    assert "sql" in F._related()["python"] and "kubernetes" in F._related()["docker"]
    c = _cand(skills=(SkillEvidence("sql", "test", 1.0), SkillEvidence("python", "declared", 1.0),
                      SkillEvidence("kubernetes", "fsp", 1.0)),
              topic_levels={"sql.aggregation": "strong", "sql.joins": "moderate"})
    # sql: test × best topic level (strong 1.0) = 1.0
    # python: max(declared 0.4, related sql 0.5 × 1.0) = 0.5
    # docker (nice): related kubernetes 0.5 × 0.8 = 0.4
    # SkillFit = (2·1.0 + 2·0.5 + 1·0.4)/5 = 0.68
    value, reasons, gaps = F.skill_fit(NEED, c)
    assert value == pytest.approx(0.68) and gaps == []
    texts = [r.text for r in reasons]
    assert "Обязательные навыки: 2 из 2" in texts and "SQL подтверждён тестом" in texts
    assert any("смежный навык SQL" in t for t in texts)


def test_skill_fit_topic_level_scales_test_evidence_and_gaps_list_missing_musts():
    c = _cand(skills=(SkillEvidence("sql", "test", 1.0),), topic_levels={"sql.aggregation": "limited"})
    # sql 0.4 (limited), python related via sql 0.5·0.4 = 0.2, docker 0 -> (0.8 + 0.4 + 0)/5 = 0.24
    value, reasons, gaps = F.skill_fit(NEED, c)
    assert value == pytest.approx(0.24) and gaps == ["Python"]
    value, reasons, gaps = F.skill_fit(NEED, _cand())
    assert value == 0.0 and gaps == ["SQL", "Python"]
    assert sum(r.kind == "minus" for r in reasons) == 2
    assert F.skill_fit(dataclasses.replace(NEED, must_skills=(), nice_skills=()), _cand())[0] == 0.5


@pytest.mark.parametrize("grade, status, adjacent, expected", [
    ("middle", "confirmed", False, 1.0), ("middle", "unconfirmed", False, 0.6),
    ("senior", "confirmed", True, 0.5), ("senior", "unconfirmed", True, 0.3),
    ("senior", "confirmed", False, 0.0), ("intern", "confirmed", True, 0.0), (None, None, True, 0.0)])
def test_grade_fit_table(grade, status, adjacent, expected):
    need = dataclasses.replace(NEED, allow_adjacent=adjacent)
    value, reasons = F.grade_fit(need, _cand(league_grade=grade, league_status=status))
    assert value == pytest.approx(expected) and reasons


@pytest.mark.parametrize("smin, smax, stype, expected", [
    (200_000, 300_000, "gross", 1.0),                       # within 320 000
    (300_000, 400_000, "gross", 0.5 + 0.5 * 20 / 100),       # 0.6
    (350_000, None, "gross", 0.5 * (1 - (30 / 320) / 0.25)),  # 0.3125
    (300_000, None, "net", 0.5 * (1 - (28_235 / 320_000) / 0.25)),   # 348 235 gross
    (500_000, 600_000, "gross", 0.0),                        # > 25 % over
    (None, None, None, 0.5),
])
def test_salary_fit_by_hand(smin, smax, stype, expected):
    value, reasons = F.salary_fit(NEED, _cand(salary_min=smin, salary_max=smax, salary_type=stype))
    assert value == pytest.approx(expected) and reasons


def test_salary_fit_is_continuous_at_the_budget():
    at = F.salary_fit(NEED, _cand(salary_min=320_000, salary_max=400_000))[0]
    above = F.salary_fit(NEED, _cand(salary_min=320_001, salary_max=None))[0]
    assert at == pytest.approx(0.5) and above == pytest.approx(0.5, abs=1e-4)


def test_semantic_fit_neutral_without_embeddings_and_mapped_with():
    assert F.semantic_fit(NEED, _cand())[0] == 0.5
    v = (1.0, 0.0)
    need = dataclasses.replace(NEED, embedding=v)
    assert F.semantic_fit(need, _cand(embedding=(1.0, 0.0)))[0] == 1.0     # cos 1
    assert F.semantic_fit(need, _cand(embedding=(0.0, 1.0)))[0] == 0.0     # cos 0
    assert F.semantic_fit(need, _cand(embedding=(0.5, math.sqrt(0.75))))[0] == pytest.approx(0.5)  # cos 0.5


# ── the score ──────────────────────────────────────────────────────────────

def test_every_component_has_a_russian_chip_and_contributions_sum_to_score():
    c = _cand(skills=(SkillEvidence("sql", "test", 1.0),), fsp_rank="kms", fsp_results=(_r("winner"),))
    s = score_candidate(NEED, c, preset("balanced"), NOW)
    assert [x.key for x in s.components] == list(COMPONENT_KEYS)
    assert s.score == pytest.approx(sum(x.contribution for x in s.components), abs=1e-12)
    assert all(x.contribution == pytest.approx(x.value * x.weight) for x in s.components)
    assert all(CYRILLIC.search(r.text) for r in s.reasons)
    for fn in (lambda: F.skill_fit(NEED, c)[1], lambda: F.grade_fit(NEED, c)[1], lambda: F.salary_fit(NEED, c)[1],
               lambda: F.semantic_fit(NEED, c)[1], lambda: F.freshness_fit(c, NOW)[1]):
        assert fn()
    assert any(r.source == "fsp" for r in s.reasons) and any(r.source == "test" for r in s.reasons)


def test_score_by_hand_for_one_candidate():
    c = _cand(skills=(SkillEvidence("sql", "test", 1.0), SkillEvidence("python", "test", 1.0),
                      SkillEvidence("docker", "declared", 1.0)),
              topic_levels={"sql.aggregation": "strong", "python.core": "moderate"}, strength=80.0)
    # skill: sql 1.0, python 0.75, docker max(0.4, —) = 0.4 -> (2 + 1.5 + 0.4)/5 = 0.78
    # strength 0.8, grade 1.0, salary 1.0 (280–300 k <= 320 k), semantic 0.5, freshness 1.0
    # score = 35·0.78 + 20·0.8 + 15·1 + 15·1 + 10·0.5 + 5·1 = 27.3 + 16 + 15 + 15 + 5 + 5 = 83.3
    s = score_candidate(NEED, c, preset("balanced"), NOW)
    assert s.score == pytest.approx(83.3)
    unconfirmed = score_candidate(NEED, dataclasses.replace(c, league_status="unconfirmed"), preset("balanced"), NOW)
    # grade drops to 0.6 (−6 points), then everything × 0.75: (83.3 − 6) · 0.75 = 57.975
    assert unconfirmed.score == pytest.approx(57.975)
    assert any("×0.75" in r.text for r in unconfirmed.reasons)


def _fixture_pool():
    sql_py = (SkillEvidence("sql", "test", 1.0), SkillEvidence("python", "test", 1.0))
    lv = {"sql.aggregation": "strong", "python.core": "strong"}
    return {
        # verified skills, strong, FSP prize-winner
        "C-ANNA": _cand("C-ANNA", skills=sql_py, topic_levels=lv, strength=88.0, fsp_rank="kms",
                        fsp_results=(_r("prize_winner"),)),
        # same skills, no FSP, a bit lower strength
        "C-ALEX": _cand("C-ALEX", skills=sql_py, topic_levels=lv, strength=78.0),
        # the same skills only declared
        "C-DECL": _cand("C-DECL", skills=(SkillEvidence("sql", "declared", 1.0),
                                          SkillEvidence("python", "declared", 1.0)), strength=78.0),
        # like Alex but did not confirm the claimed grade
        "C-UNCF": _cand("C-UNCF", skills=sql_py, topic_levels=lv, strength=78.0, league_status="unconfirmed"),
        # like Alex but expects 40 % over the budget
        "C-EXPN": _cand("C-EXPN", skills=sql_py, topic_levels=lv, strength=78.0, salary_min=450_000,
                        salary_max=500_000),
        # like Alex but inactive for half a year
        "C-IDLE": _cand("C-IDLE", skills=sql_py, topic_levels=lv, strength=78.0,
                        last_active_at=NOW - datetime.timedelta(days=180)),
        # no relevant skills at all
        "C-NONE": _cand("C-NONE", strength=78.0),
    }


def test_hand_ranked_pool():
    pool = _fixture_pool()
    out = score_pool(NEED, list(pool.values()), preset("balanced"), NOW)
    order = [s.public_id for s in out]
    rank = {pid: i for i, pid in enumerate(order)}
    assert order[0] == "C-ANNA"
    # each pair differs in one property only; the better one must rank higher
    for better, worse in [("C-ALEX", "C-DECL"), ("C-ALEX", "C-UNCF"), ("C-ALEX", "C-EXPN"),
                          ("C-ALEX", "C-IDLE"), ("C-DECL", "C-NONE"), ("C-ANNA", "C-ALEX")]:
        assert rank[better] < rank[worse], (better, worse, order)
    assert next(s for s in out if s.public_id == "C-NONE").gaps == ("SQL", "Python")


def test_presets_change_the_order_the_way_their_names_say():
    pool = _fixture_pool()
    expensive = pool["C-EXPN"]
    cheap_decl = pool["C-DECL"]
    skills_first = {s.public_id: s.score for s in score_pool(NEED, [expensive, cheap_decl], preset("skills"), NOW)}
    budget_first = {s.public_id: s.score for s in score_pool(NEED, [expensive, cheap_decl], preset("budget"), NOW)}
    assert skills_first["C-EXPN"] > skills_first["C-DECL"]      # verified skills win
    assert budget_first["C-DECL"] > budget_first["C-EXPN"]      # affordable wins


def test_score_pool_is_deterministic_and_validates_weights():
    pool = list(_fixture_pool().values())
    a = score_pool(NEED, pool, preset("balanced"), NOW)
    b = score_pool(NEED, pool[::-1], preset("balanced"), NOW)
    assert a == b
    with pytest.raises(ValueError):
        score_pool(NEED, [], Weights(-1, 0, 0, 0, 0, 0), NOW)
