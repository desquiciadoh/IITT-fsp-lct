"""Matching DTOs (ML.md §3). BE loads them from the ORM in one batch; the engine never sees models."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Literal

Spec = Literal["backend", "frontend", "ml_data"]
Grade = Literal["intern", "junior", "middle", "senior"]
Source = Literal["test", "fsp", "microtask", "declared"]
Tier = Literal["winner", "prize_winner", "finalist", "participant"]
Rank = Literal["cat3", "cat2", "cat1", "kms", "ms"]
SalaryType = Literal["gross", "net"]
ComponentKey = Literal["skill", "strength", "grade", "salary", "semantic", "freshness"]

GRADES: tuple[str, ...] = ("intern", "junior", "middle", "senior")
SOURCES: tuple[str, ...] = ("test", "fsp", "microtask", "declared")
TIERS: tuple[str, ...] = ("winner", "prize_winner", "finalist", "participant")
RANKS: tuple[str, ...] = ("cat3", "cat2", "cat1", "kms", "ms")
SALARY_TYPES: tuple[str, ...] = ("gross", "net")
LEAGUE_STATUSES: tuple[str, ...] = ("pending", "confirmed", "unconfirmed")
COMPONENT_KEYS: tuple[str, ...] = ("skill", "strength", "grade", "salary", "semantic", "freshness")


@dataclass(frozen=True)
class SkillEvidence:
    skill_id: str
    source: Source
    level: float          # 0..1; BE passes 1.0 when it has no finer level


@dataclass(frozen=True)
class FspResultCtx:
    tier: Tier
    date: datetime.date
    discipline: str
    participants_total: int
    team_size: int | None


@dataclass(frozen=True)
class CandidateCtx:
    public_id: str
    specialization: Spec | None
    league_grade: Grade | None
    league_status: Literal["pending", "confirmed", "unconfirmed"] | None
    theta: float | None
    se: float | None
    rating: int | None
    percentile: float | None
    strength: float | None                      # precomputed by strength(), stored by BE
    skills: tuple[SkillEvidence, ...]
    topic_levels: dict[str, str]                # from CatResult.topics (a dict: the DTO is not hashable)
    fsp_rank: Rank | None
    fsp_results: tuple[FspResultCtx, ...]
    salary_min: int | None
    salary_max: int | None
    salary_type: SalaryType | None
    work_formats: tuple[str, ...]
    city: str
    timezone: str
    last_active_at: datetime.datetime | None
    embedding: tuple[float, ...] | None = None              # P1 (ML-9)
    microtask_dates: tuple[datetime.date, ...] = ()        # accepted micro-tasks, for activity
    embedding_model: str | None = None                      # embeddings.active_model_id() of `embedding`


@dataclass(frozen=True)
class NeedCtx:
    position_id: str
    specialization: Spec
    grades: tuple[Grade, ...]
    allow_adjacent: bool
    must_skills: tuple[str, ...]                # skill ids (normalized at save time)
    nice_skills: tuple[str, ...]
    work_formats: tuple[str, ...]
    location: str
    salary_min: int
    salary_max: int
    salary_type: SalaryType
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None


@dataclass(frozen=True)
class Weights:
    skill: float = 35
    strength: float = 20
    grade: float = 15
    salary: float = 15
    semantic: float = 10
    freshness: float = 5

    def as_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in COMPONENT_KEYS}


@dataclass(frozen=True)
class Component:
    key: ComponentKey
    value: float          # 0..1
    weight: float         # effective weight: weights rescaled to Σ = 100 (× 0.75 if unconfirmed)
    contribution: float   # value · weight; Σ contribution == Scored.score


@dataclass(frozen=True)
class Reason:
    kind: Literal["plus", "minus", "info"]
    text: str             # Russian, user-facing (e.g. "SQL подтверждён тестом")
    source: Source | None


@dataclass(frozen=True)
class Scored:
    public_id: str
    score: float                                # 0..100
    components: tuple[Component, ...]
    reasons: tuple[Reason, ...]
    gaps: tuple[str, ...]
