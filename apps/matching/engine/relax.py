"""Counterfactual relaxations and acceptance likelihood (ML.md §3, P1). ML-0 stubs; ML-10 implements them."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .types import CandidateCtx, NeedCtx, Weights


@dataclass(frozen=True)
class Relaxation:
    change: str     # "убрать Kubernetes из обязательных"
    delta: int      # +23 candidates


def relaxations(need: NeedCtx, pool: Sequence[CandidateCtx], weights: Weights) -> list[Relaxation]:
    return []


def acceptance_likelihood(need: NeedCtx, offer_salary_max: int,
                          c: CandidateCtx) -> Literal["low", "medium", "high"]:
    return "medium"
