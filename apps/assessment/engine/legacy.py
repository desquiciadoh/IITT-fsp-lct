"""Legacy item families and scorer behind the pre-CAT BE API (ML-0 compatibility shim).

BE's services still call `FAMILIES_REGISTRY` and `score_assessment` (the old
`assessment/engine.py` API). They stay importable from `assessment.engine` until BE
swaps in `CatEngine` (BE.md N2); after that this module is deleted.

CRITICAL INVARIANTS:
1. LLM NEVER decides score or grade! All items are generated from parametric
   templates with a deterministic Python oracle.
2. The correct answer (key) is kept server-side only in assessment_items.key
   and is NEVER serialized in any client-facing response.
"""
import random
from dataclasses import dataclass
from typing import Any


# String constants instead of core.enums: engine packages are pure (CLAUDE.md invariant 6).
# tests/ml/test_contract.py checks these against core.enums.
class Grade:
    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"


class GradeDecision:
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"


class Specialization:
    BACKEND = "backend"
    FRONTEND = "frontend"
    ML_DATA = "ml_data"


@dataclass
class ItemInstance:
    family_id: str
    stem_md: str
    code: dict[str, str] | None
    options: list[dict[str, str]] | None
    input_type: str  # 'choice', 'number', 'text'
    key: Any  # SERVER-SIDE ONLY!
    fingerprint: str
    time_limit_s: int


class BaseItemFamily:
    family_id: str
    topic: str
    spec: str
    difficulty_b: float  # IRT b parameter
    discrimination_a: float = 1.2  # IRT a parameter
    guessing_c: float = 0.25  # IRT c parameter
    time_limit_s: int = 120

    def generate(self, seed: str) -> ItemInstance:
        raise NotImplementedError

    def oracle(self, instance_data: dict) -> Any:
        raise NotImplementedError


# --- Adapters: the ML-1 families behind the legacy generate(seed: str) API ---

class _LegacyAdapter(BaseItemFamily):
    """Serves an ItemFamily (families/) through the old interface BE's services call.

    Keys are option ids drawn from rng (ML-F1 fixed): BE's `answer == key` check stays valid.
    `time_limit_s` and `legacy_b` keep the legacy per-item limits and difficulties that BE's
    lifecycle tests pin through `score_assessment` (θ = mean b + ...). The real IRT priors are
    in `family.meta`; the CAT engine uses those.
    """

    def __init__(self, family, spec: str, time_limit_s: int, legacy_b: float):
        m = family.meta
        self._family = family
        self.family_id = m.id
        self.topic = m.topic
        self.spec = spec
        self.difficulty_b = legacy_b
        self.discrimination_a = m.a
        self.guessing_c = m.c
        self.time_limit_s = time_limit_s

    def generate(self, seed: str) -> ItemInstance:
        inst = self._family.generate(random.Random(seed))   # str seeds hash with sha512: stable
        view = inst.view()
        return ItemInstance(
            family_id=self.family_id, stem_md=view["stem_md"], code=view["code"],
            options=view["options"], input_type=view["input"], key=inst.key,
            fingerprint=inst.fingerprint, time_limit_s=self.time_limit_s,
        )


def _build_registry() -> dict[str, BaseItemFamily]:
    from ..families.backend.sql_group_having import FAMILY as sql
    from ..families.frontend.js_event_loop import FAMILY as event_loop
    from ..families.shared.complexity import FAMILY as complexity

    adapters = [
        _LegacyAdapter(sql, Specialization.BACKEND, 90, legacy_b=0.4),
        _LegacyAdapter(complexity, Specialization.BACKEND, 60, legacy_b=0.8),
        _LegacyAdapter(event_loop, Specialization.FRONTEND, 60, legacy_b=0.5),
    ]
    return {a.family_id: a for a in adapters}


FAMILIES_REGISTRY: dict[str, BaseItemFamily] = _build_registry()


# --- IRT Scoring (Item Response Theory) ---

GRADE_CUTS = {
    Grade.INTERN: -1.0,
    Grade.JUNIOR: -0.2,
    Grade.MIDDLE: 0.6,
    Grade.SENIOR: 1.5,
}


def score_assessment(items_data: list[dict]) -> tuple[float, float, int, str, str]:
    """Calculate θ (theta), SE, rating (1000 + 200θ), and grade decision.

    Deterministic IRT EAP estimation from item responses.
    Returns:
        theta: float
        se: float
        rating: int (sport-style rating, e.g. 1000 + 200*theta)
        result_grade: Grade
        decision: GradeDecision ('confirmed' or 'unconfirmed')
    """
    if not items_data:
        return 0.0, 0.5, 1000, Grade.JUNIOR, GradeDecision.UNCONFIRMED

    # Simple robust EAP approximation:
    # theta = sum((correct - c) * b) / sum(a) ...
    correct_count = sum(1 for item in items_data if item.get('correct'))
    total_count = len(items_data)
    pct = correct_count / total_count if total_count > 0 else 0

    # Theta mapped from accuracy and average difficulty
    avg_b = sum(item.get('b', 0.5) for item in items_data) / total_count
    theta = round(avg_b + (pct - 0.5) * 2.0, 2)
    se = round(max(0.2, 1.0 / (total_count ** 0.5)), 2)
    rating = int(1000 + 200 * theta)

    # Determine grade based on theta cutoffs
    if theta >= GRADE_CUTS[Grade.SENIOR]:
        result_grade = Grade.SENIOR
    elif theta >= GRADE_CUTS[Grade.MIDDLE]:
        result_grade = Grade.MIDDLE
    elif theta >= GRADE_CUTS[Grade.JUNIOR]:
        result_grade = Grade.JUNIOR
    else:
        result_grade = Grade.INTERN

    return theta, se, rating, result_grade, GradeDecision.CONFIRMED
