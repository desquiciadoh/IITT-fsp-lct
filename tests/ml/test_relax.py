"""Tests for ML-10 (Counterfactual relaxations and acceptance likelihood).

Pure tests: no DB, no network, runs under pytest tests/ml.
"""
from __future__ import annotations

import datetime
from typing import Literal

import pytest
from matching.engine import relax as R
from matching.engine.types import CandidateCtx, NeedCtx, SkillEvidence


def _need(
    must_skills=("python", "postgresql"),
    grades=("middle",),
    allow_adjacent=False,
    work_formats=("remote",),
    salary_max=250_000,
) -> NeedCtx:
    return NeedCtx(
        position_id="P-TEST",
        specialization="backend",
        grades=grades,
        allow_adjacent=allow_adjacent,
        must_skills=must_skills,
        nice_skills=(),
        work_formats=work_formats,
        location="Москва",
        salary_min=150_000,
        salary_max=salary_max,
        salary_type="gross",
        embedding=None,
    )


def _cand(
    pid: str,
    skills: tuple[str, ...] = ("python", "postgresql"),
    grade: str = "middle",
    work_formats=("remote",),
    salary_min: int | None = 200_000,
    salary_max: int | None = 240_000,
    status: Literal["confirmed", "unconfirmed", "pending"] = "confirmed",
    last_active_days_ago: int | None = 2,
) -> CandidateCtx:
    dt = None
    if last_active_days_ago is not None:
        dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=last_active_days_ago)

    ev_list = tuple(SkillEvidence(s, "test", 1.0) for s in skills)
    return CandidateCtx(
        public_id=pid,
        specialization="backend",
        league_grade=grade,
        league_status=status,
        theta=0.5,
        se=0.2,
        rating=1100,
        percentile=70.0,
        strength=75.0,
        skills=ev_list,
        topic_levels={},
        fsp_rank=None,
        fsp_results=(),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_type="gross",
        work_formats=work_formats,
        city="Москва",
        timezone="UTC+3",
        last_active_at=dt,
        embedding=None,
    )


# ── relaxations ────────────────────────────────────────────────────────────

def test_relaxations_empty_pool():
    need = _need()
    assert R.relaxations(need, []) == []


def test_relaxations_must_skills():
    need = _need(must_skills=("python", "postgresql", "kubernetes"))
    pool = [
        _cand("C-1", skills=("python", "postgresql", "kubernetes")),  # baseline qualified
        _cand("C-2", skills=("python", "postgresql")),                # lacks kubernetes
        _cand("C-3", skills=("python", "postgresql")),                # lacks kubernetes
        _cand("C-4", skills=("python", "kubernetes")),                # lacks postgresql
        _cand("C-5", skills=("python",)),                             # lacks both
    ]
    rel = R.relaxations(need, pool)
    # Removing kubernetes adds C-2 and C-3 (+2)
    # Removing postgresql adds C-4 (+1)
    changes = {r.change: r.delta for r in rel}
    assert "убрать Kubernetes из обязательных" in changes
    assert changes["убрать Kubernetes из обязательных"] == 2
    assert "убрать PostgreSQL из обязательных" in changes
    assert changes["убрать PostgreSQL из обязательных"] == 1


def test_relaxations_allow_adjacent():
    need = _need(grades=("middle",), allow_adjacent=False)
    pool = [
        _cand("C-MID", grade="middle"),
        _cand("C-JUN", grade="junior"),  # adjacent
        _cand("C-SEN", grade="senior"),  # adjacent
        _cand("C-INT", grade="intern"),  # not adjacent to middle
    ]
    rel = R.relaxations(need, pool)
    adj = next((r for r in rel if r.change == "разрешить смежные грейды"), None)
    assert adj is not None
    assert adj.delta == 2  # C-JUN and C-SEN


def test_relaxations_add_work_format():
    need = _need(work_formats=("office",))
    pool = [
        _cand("C-OFF", work_formats=("office",)),
        _cand("C-REM1", work_formats=("remote",)),
        _cand("C-REM2", work_formats=("remote",)),
        _cand("C-HYB", work_formats=("hybrid",)),
    ]
    rel = R.relaxations(need, pool)
    changes = {r.change: r.delta for r in rel}
    assert "добавить удалённый формат" in changes
    assert changes["добавить удалённый формат"] == 2
    assert "добавить гибридный формат" in changes
    assert changes["добавить гибридный формат"] == 1


def test_relaxations_increase_budget():
    need = _need(salary_max=200_000)
    pool = [
        _cand("C-FIT", salary_min=180_000, salary_max=200_000),      # fits
        _cand("C-SLIGHT1", salary_min=220_000, salary_max=250_000),  # fits under 240k (200k * 1.20)
        _cand("C-SLIGHT2", salary_min=230_000, salary_max=260_000),  # fits under 240k
        _cand("C-FAR", salary_min=350_000, salary_max=400_000),      # does not fit 240k
    ]
    rel = R.relaxations(need, pool)
    sal = next((r for r in rel if "бюджет" in r.change), None)
    assert sal is not None
    assert sal.delta == 2  # C-SLIGHT1 and C-SLIGHT2


def test_relaxations_capped_at_top_3_and_sorted_desc():
    need = _need(
        must_skills=("python", "postgresql", "kubernetes", "docker"),
        allow_adjacent=False,
        work_formats=("office",),
        salary_max=200_000,
    )
    # Construct a pool that triggers multiple relaxations with distinct deltas
    pool = []
    # 5 candidates lacking kubernetes
    for i in range(5):
        pool.append(_cand(f"C-K8S-{i}", skills=("python", "postgresql", "docker"), work_formats=("office",)))
    # 3 candidates with adjacent junior grade
    for i in range(3):
        pool.append(_cand(f"C-JUN-{i}", skills=("python", "postgresql", "kubernetes", "docker"),
                          grade="junior", work_formats=("office",)))
    # 2 candidates wanting remote
    for i in range(2):
        pool.append(_cand(f"C-REM-{i}", skills=("python", "postgresql", "kubernetes", "docker"),
                          work_formats=("remote",)))
    # 1 candidate wanting higher salary
    pool.append(_cand("C-SAL-0", skills=("python", "postgresql", "kubernetes", "docker"),
                      salary_min=220_000, work_formats=("office",)))

    rel = R.relaxations(need, pool)
    assert len(rel) <= 3
    # Check descending order by delta
    deltas = [r.delta for r in rel]
    assert deltas == sorted(deltas, reverse=True)
    assert deltas[0] >= deltas[1] >= deltas[2]
    assert rel[0].change == "убрать Kubernetes из обязательных"
    assert rel[0].delta == 5


# ── acceptance_likelihood ──────────────────────────────────────────────────

def test_acceptance_likelihood_high():
    need = _need(salary_max=250_000, work_formats=("remote",))
    # Candidate asks 180-220k, offer is 250k (exceeds expectations), format matches, active 2 days ago
    c = _cand("C-1", salary_min=180_000, salary_max=220_000, work_formats=("remote",),
              status="confirmed", last_active_days_ago=2)
    assert R.acceptance_likelihood(need, offer_salary_max=250_000, c=c) == "high"


def test_acceptance_likelihood_medium():
    need = _need(salary_max=200_000, work_formats=("remote",))
    # Candidate asks 190-240k, offer is 200k (within min-max range), active 20 days ago
    c = _cand("C-1", salary_min=190_000, salary_max=240_000, work_formats=("remote",),
              status="confirmed", last_active_days_ago=20)
    assert R.acceptance_likelihood(need, offer_salary_max=200_000, c=c) == "medium"


def test_acceptance_likelihood_low_when_offer_far_below_minimum():
    need = _need(salary_max=120_000, work_formats=("remote",))
    # Candidate minimum is 200k, offer is 120k (60% of minimum -> way below floor)
    c = _cand("C-1", salary_min=200_000, salary_max=250_000, work_formats=("remote",),
              status="confirmed", last_active_days_ago=1)
    assert R.acceptance_likelihood(need, offer_salary_max=120_000, c=c) == "low"


def test_acceptance_likelihood_format_mismatch():
    need = _need(salary_max=250_000, work_formats=("office",))
    # Candidate wants remote only, position is office only
    c = _cand("C-1", salary_min=180_000, salary_max=220_000, work_formats=("remote",),
              status="confirmed", last_active_days_ago=2)
    # Even with high salary, format conflict pulls score down
    assert R.acceptance_likelihood(need, offer_salary_max=250_000, c=c) in ("low", "medium")
