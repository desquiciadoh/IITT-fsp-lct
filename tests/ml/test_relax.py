"""ML-10: counterfactual relaxations and acceptance likelihood. Pure, fixed clock, hand-computed goldens."""
from __future__ import annotations

import datetime
from typing import Literal

from matching.engine import relax as R
from matching.engine.salary import to_gross
from matching.engine.types import CandidateCtx, NeedCtx, SkillEvidence

NOW = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.timezone.utc)


def _need(must_skills=("python", "postgresql"), grades=("middle",), allow_adjacent=False, work_formats=("remote",),
          salary_max=250_000, salary_type="gross") -> NeedCtx:
    return NeedCtx(position_id="P-TEST", specialization="backend", grades=grades, allow_adjacent=allow_adjacent,
                   must_skills=must_skills, nice_skills=(), work_formats=work_formats, location="Москва",
                   salary_min=150_000, salary_max=salary_max, salary_type=salary_type, embedding=None)


def _cand(pid: str, skills=("python", "postgresql"), grade="middle", work_formats=("remote",),
          salary_min: int | None = 200_000, salary_max: int | None = 240_000,
          status: Literal["confirmed", "unconfirmed", "pending"] = "confirmed",
          days_ago: int | None = 2) -> CandidateCtx:
    seen = None if days_ago is None else NOW - datetime.timedelta(days=days_ago)
    return CandidateCtx(public_id=pid, specialization="backend", league_grade=grade, league_status=status, theta=0.5,
                        se=0.2, rating=1100, percentile=70.0, strength=75.0,
                        skills=tuple(SkillEvidence(s, "test", 1.0) for s in skills), topic_levels={}, fsp_rank=None,
                        fsp_results=(), salary_min=salary_min, salary_max=salary_max, salary_type="gross",
                        work_formats=work_formats, city="Москва", timezone="UTC+3", last_active_at=seen,
                        embedding=None)


# ── qualification: one rule with the score ─────────────────────────────────

def test_qualifies_uses_hard_filters_gaps_and_salary_fit():
    need = _need(salary_max=200_000)
    assert R.qualifies(need, _cand("ok"))
    assert not R.qualifies(need, _cand("gap", skills=("python",)))                  # a must-have gap chip
    assert not R.qualifies(need, _cand("grade", grade="senior"))                    # hard filter
    assert R.qualifies(need, _cand("near", salary_min=240_000, salary_max=260_000))  # SalaryFit > 0 below 125 %
    assert not R.qualifies(need, _cand("far", salary_min=250_000, salary_max=300_000))  # 0 from 125 % on


# ── relaxations ────────────────────────────────────────────────────────────

def test_relaxations_empty_pool():
    assert R.relaxations(_need(), []) == []


def test_relaxations_count_added_candidates_over_a_nonzero_baseline():
    need = _need(must_skills=("python", "postgresql", "kubernetes"))
    pool = [_cand("C-1", skills=("python", "postgresql", "kubernetes")),      # qualifies already
            _cand("C-2", skills=("python", "postgresql", "kubernetes")),      # qualifies already
            _cand("C-3", skills=("python", "postgresql")), _cand("C-4", skills=("python", "postgresql")),
            _cand("C-5", skills=("python", "kubernetes")), _cand("C-6", skills=("python",))]
    assert R._count(need, pool) == 2
    assert R.relaxations(need, pool) == [R.Relaxation("убрать Kubernetes из обязательных", 2),
                                         R.Relaxation("убрать PostgreSQL из обязательных", 1)]


def test_relaxations_grades_and_formats():
    need = _need(work_formats=("office",))
    pool = [_cand("M", work_formats=("office",)), _cand("J", grade="junior", work_formats=("office",)),
            _cand("S", grade="senior", work_formats=("office",)), _cand("I", grade="intern", work_formats=("office",)),
            _cand("R1"), _cand("R2"), _cand("H", work_formats=("hybrid",))]
    assert R.relaxations(need, pool) == [R.Relaxation("добавить удалённый формат", 2),
                                         R.Relaxation("разрешить смежные грейды", 2),
                                         R.Relaxation("добавить гибридный формат", 1)]   # ties by text


def test_relaxation_budget_matches_the_salary_component():
    need = _need(salary_max=200_000)
    pool = [_cand("fit", salary_min=180_000, salary_max=200_000),
            _cand("near", salary_min=260_000, salary_max=280_000),    # 0 at 250k; > 0 once the zero moves to 300k
            _cand("near2", salary_min=290_000, salary_max=320_000),
            _cand("far", salary_min=350_000, salary_max=400_000)]
    assert R.relaxations(need, pool) == [R.Relaxation("увеличить бюджет на 20 %", 2)]


def test_relaxations_top3_sorted():
    need = _need(must_skills=("python", "postgresql", "kubernetes", "docker"), work_formats=("office",),
                 salary_max=200_000)
    full = ("python", "postgresql", "kubernetes", "docker")
    pool = ([_cand(f"K{i}", skills=("python", "postgresql", "docker"), work_formats=("office",)) for i in range(5)]
            + [_cand(f"J{i}", skills=full, grade="junior", work_formats=("office",)) for i in range(3)]
            + [_cand(f"R{i}", skills=full) for i in range(2)]
            + [_cand("S", skills=full, salary_min=260_000, salary_max=270_000, work_formats=("office",))])
    assert R.relaxations(need, pool) == [R.Relaxation("убрать Kubernetes из обязательных", 5),
                                         R.Relaxation("разрешить смежные грейды", 3),
                                         R.Relaxation("добавить удалённый формат", 2)]


# ── acceptance likelihood: hand-computed totals ────────────────────────────

def test_high_when_everything_fits():
    # salary 1.0 (offer ≥ 1.05·max), format 1, recency 1 (2 days), confirmed 1 -> total 1.0
    c = _cand("C", salary_min=180_000, salary_max=220_000)
    assert R.acceptance_likelihood(_need(), 250_000, c, NOW) == "high"


def test_medium_inside_the_range():
    # salary 0.40 + 0.50·(200−190)/50 = 0.50; recency 20 days 0.75 -> 0.20 + 0.25 + 0.15 + 0.15 = 0.75
    c = _cand("C", salary_min=190_000, salary_max=240_000, days_ago=20)
    assert R.acceptance_likelihood(_need(salary_max=200_000), 200_000, c, NOW) == "medium"


def test_threshold_078_by_hand():
    # range 100k..200k, recency 0.75: total = 0.4·s + 0.55, high iff s ≥ 0.575 iff offer ≥ 135k
    c = _cand("C", salary_min=100_000, salary_max=200_000, days_ago=20)
    assert R.acceptance_likelihood(_need(), 136_000, c, NOW) == "high"
    assert R.acceptance_likelihood(_need(), 134_000, c, NOW) == "medium"


def test_low_far_below_minimum_and_format_conflict_caps_at_medium():
    c = _cand("C", salary_min=200_000, salary_max=250_000, days_ago=1)
    assert R.acceptance_likelihood(_need(), 120_000, c, NOW) == "low"           # < 0.75·minimum
    # conflict: salary 1, format 0, recency 1, status 1 -> 0.75, capped at medium
    office = _cand("O", salary_min=180_000, salary_max=220_000, work_formats=("office",))
    assert R.acceptance_likelihood(_need(), 250_000, office, NOW) == "medium"


def test_no_declared_salary_and_the_clock():
    # 0.55·0.4 + 0.25 + 0.20 + 0.15 = 0.82 -> high; 40 days later recency 0.5 -> 0.72 -> medium
    c = _cand("C", salary_min=None, salary_max=None, days_ago=2)
    assert R.acceptance_likelihood(_need(), 200_000, c, NOW) == "high"
    assert R.acceptance_likelihood(_need(), 200_000, c, NOW + datetime.timedelta(days=40)) == "medium"


def test_status_and_net_offers():
    pending = _cand("P", salary_min=None, salary_max=None, status="pending")        # 0.22+0.25+0.2+0.105 = 0.775
    assert R.acceptance_likelihood(_need(), 200_000, pending, NOW) == "medium"
    c = _cand("C", salary_min=190_000, salary_max=240_000)
    net = R.acceptance_likelihood(_need(salary_type="net"), 180_000, c, NOW)
    assert net == R.acceptance_likelihood(_need(), to_gross(180_000, "net"), c, NOW)
