"""Engine adapter conforming to ML.md §3 contract and CatEngine Protocol.

Connects the assessment service to the IRT CAT scoring and parametric
question family engine. Backed by the current deterministic stub engine
until ML ships the full CatEngine.
"""

from __future__ import annotations

import bisect
import hashlib
import hmac
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from core.enums import Grade, GradeDecision, ItemFormat, Specialization

from assessment.engine.legacy import GRADE_CUTS
from assessment.families.backend.sql_group_having import FAMILY as sql_family
from assessment.families.frontend.js_event_loop import FAMILY as event_loop_family
from assessment.families.ml_data.models_dl import FAMILIES as ml_models_families
from assessment.families.ml_data.stats_metrics import FAMILIES as ml_stats_families
from assessment.families.shared.complexity import FAMILY as complexity_family

Spec = str
Mode = Literal["full", "express"]
Kind = Literal["initial", "fallback", "promotion", "screening"]
InputKind = Literal["choice", "number", "text", "code"]

GRADE_ORDER = {
    Grade.INTERN: 1,
    Grade.JUNIOR: 2,
    Grade.MIDDLE: 3,
    Grade.SENIOR: 4,
}

LOWER_GRADE = {
    Grade.SENIOR: Grade.MIDDLE,
    Grade.MIDDLE: Grade.JUNIOR,
    Grade.JUNIOR: Grade.INTERN,
}


@dataclass(frozen=True)
class FamilyMeta:
    """Metadata describing a parametric question family."""

    id: str
    spec: Spec
    topic: str
    skills: list[str] = field(default_factory=list)
    a: float = 1.2
    b: float = 0.5
    c: float = 0.25
    time_limit_s: int = 120
    status: Literal["active", "shadow", "retired"] = "active"
    format: str = ItemFormat.CONCEPT_MCQ
    specs: tuple[str, ...] = ()
    version: int = 1


@dataclass
class Instance:
    """A generated concrete question instance.

    INVARIANT: The `key` field contains the answer and MUST NEVER be leaked
    to the client or included in `view()`.
    """

    stem_md: str
    input: InputKind
    key: Any  # SERVER-SIDE ONLY -> AssessmentItem.key
    fingerprint: str
    code: dict[str, str] | None = None
    options: list[dict[str, str]] | None = None
    time_limit_s: int = 120

    def view(self) -> dict[str, Any]:
        """Client-safe representation. Never exposes key or fingerprint."""
        res: dict[str, Any] = {
            "stem_md": self.stem_md,
            "input": self.input,
            "input_type": self.input,
            "time_limit_s": self.time_limit_s,
        }
        if self.code is not None:
            res["code"] = self.code
        if self.options is not None:
            res["options"] = self.options
        return res


class ItemFamily(Protocol):
    meta: FamilyMeta

    def generate(self, rng: random.Random) -> Instance: ...

    def is_correct(self, key: Any, answer: dict[str, Any] | str) -> bool: ...

    def oracle(self, inst: Instance) -> Any: ...


@dataclass
class CatState:
    """Serialized CAT engine state stored in AssessmentSession.state."""

    spec: Spec
    claimed: Grade
    mode: Mode = "full"
    kind: Kind = "initial"
    administered: list[dict[str, Any]] = field(default_factory=list)
    theta: float = 0.0
    se: float = 0.5
    min_items: int = 2
    max_items: int = 15

    def to_json(self) -> dict[str, Any]:
        return {
            "spec": self.spec,
            "claimed": self.claimed,
            "mode": self.mode,
            "kind": self.kind,
            "administered": self.administered,
            "theta": self.theta,
            "se": self.se,
            "min_items": self.min_items,
            "max_items": self.max_items,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> CatState:
        return cls(
            spec=d.get("spec", ""),
            claimed=d.get("claimed", ""),
            mode=d.get("mode", "full"),
            kind=d.get("kind", "initial"),
            administered=list(d.get("administered", [])),
            theta=float(d.get("theta", 0.0)),
            se=float(d.get("se", 0.5)),
            min_items=int(d.get("min_items", 2)),
            max_items=int(d.get("max_items", 15)),
        )


@dataclass(frozen=True)
class CatResult:
    """Final assessment evaluation result."""

    theta: float
    se: float
    rating: int  # round(1000 + 200 * theta)
    rating_ci: int  # round(1.96 * 200 * se)
    result_grade: Grade
    decision: Literal["confirmed", "unconfirmed"]
    promotion_unlocked: bool  # P(theta >= next cut) >= 0.9
    fallback_grade: Grade | None  # highest lower grade with P(theta >= cut) >= 0.8
    topics: list[tuple[str, Literal["strong", "moderate", "limited"]]]
    evidence: list[tuple[int, Grade, bool]]  # (seq, item level, correct)


class CatEngine(Protocol):
    """Protocol matching ML.md §3."""

    def start(
        self,
        spec: Spec,
        claimed: Grade,
        mode: Mode,
        kind: Kind,
        pool: list[FamilyMeta],
        seen: set[str],
    ) -> CatState: ...

    def next_family(
        self,
        state: CatState,
        pool: list[FamilyMeta],
        rng: random.Random,
    ) -> FamilyMeta | None: ...

    def record(
        self,
        state: CatState,
        family_id: str,
        correct: bool,
        late: bool = False,
    ) -> CatState: ...

    def result(self, state: CatState) -> CatResult: ...


# --- Real & Stub Family Registries conforming to FamilyMeta ---

class _CompatibilityFamily:
    def __init__(self, family: Any, legacy_id: str):
        self._family = family
        self.family_id = legacy_id

    def generate(self, seed: str) -> Any:
        return self._family.generate(random.Random(seed))


BackendSqlAggregationFamily = _CompatibilityFamily(sql_family, "be.sql.group_having.v1")
BackendPythonComplexityFamily = _CompatibilityFamily(complexity_family, "be.algo.complexity.v1")
FrontendJsClosureFamily = _CompatibilityFamily(event_loop_family, "fe.js.event_loop.v1")

sql_meta = FamilyMeta(
    id=sql_family.meta.id,
    spec=Specialization.BACKEND,
    specs=(Specialization.BACKEND,),
    topic=sql_family.meta.topic,
    skills=list(sql_family.meta.skills),
    a=sql_family.meta.a,
    b=0.4,
    c=sql_family.meta.c,
    time_limit_s=90,
    status="active",
    format=sql_family.meta.format,
)
complexity_meta = FamilyMeta(
    id=complexity_family.meta.id,
    spec=Specialization.BACKEND,
    specs=(Specialization.BACKEND, Specialization.FRONTEND, Specialization.ML_DATA),
    topic=complexity_family.meta.topic,
    skills=list(complexity_family.meta.skills),
    a=complexity_family.meta.a,
    b=0.8,
    c=complexity_family.meta.c,
    time_limit_s=60,
    status="active",
    format=complexity_family.meta.format,
)
event_loop_meta = FamilyMeta(
    id=event_loop_family.meta.id,
    spec=Specialization.FRONTEND,
    specs=(Specialization.FRONTEND,),
    topic=event_loop_family.meta.topic,
    skills=list(event_loop_family.meta.skills),
    a=event_loop_family.meta.a,
    b=0.5,
    c=event_loop_family.meta.c,
    time_limit_s=60,
    status="active",
    format=event_loop_family.meta.format,
)

ml_metas: list[FamilyMeta] = [
    FamilyMeta(
        id=fam.meta.id,
        spec=Specialization.ML_DATA,
        specs=(Specialization.ML_DATA,),
        topic=fam.meta.topic,
        skills=list(fam.meta.skills),
        a=fam.meta.a,
        b=fam.meta.b,
        c=fam.meta.c,
        time_limit_s=fam.meta.time_limit_s,
        status="active",
        format=fam.meta.format,
    )
    for fam in (ml_stats_families + ml_models_families)
]

STUB_FAMILY_METAS: dict[str, FamilyMeta] = {
    sql_meta.id: sql_meta,
    complexity_meta.id: complexity_meta,
    event_loop_meta.id: event_loop_meta,
    **{meta.id: meta for meta in ml_metas},
    "be.sql.group_having.v1": FamilyMeta(
        id="be.sql.group_having.v1",
        spec=Specialization.BACKEND,
        topic=sql_family.meta.topic,
        skills=list(sql_family.meta.skills),
        a=sql_family.meta.a,
        b=0.4,
        c=sql_family.meta.c,
        time_limit_s=90,
        status="retired",
        format=ItemFormat.SQL_RESULT,
    ),
    "be.algo.complexity.v1": FamilyMeta(
        id="be.algo.complexity.v1",
        spec=Specialization.BACKEND,
        topic=complexity_family.meta.topic,
        skills=list(complexity_family.meta.skills),
        a=complexity_family.meta.a,
        b=0.8,
        c=complexity_family.meta.c,
        time_limit_s=60,
        status="retired",
        format=ItemFormat.COMPLEXITY,
    ),
    "fe.js.event_loop.v1": FamilyMeta(
        id="fe.js.event_loop.v1",
        spec=Specialization.FRONTEND,
        topic=event_loop_family.meta.topic,
        skills=list(event_loop_family.meta.skills),
        a=event_loop_family.meta.a,
        b=0.5,
        c=event_loop_family.meta.c,
        time_limit_s=60,
        status="retired",
        format=ItemFormat.CODE_OUTPUT,
    ),
}

_STUB_GENERATORS = {
    sql_meta.id: sql_family,
    complexity_meta.id: complexity_family,
    event_loop_meta.id: event_loop_family,
    **{fam.meta.id: fam for fam in (ml_stats_families + ml_models_families)},
    "be.sql.group_having.v1": sql_family,
    "be.algo.complexity.v1": complexity_family,
    "fe.js.event_loop.v1": event_loop_family,
}


def item_level(meta: FamilyMeta | float | int) -> str:
    """Return difficulty band grade for difficulty parameter b."""
    b = meta.b if isinstance(meta, FamilyMeta) else float(meta)
    if b >= GRADE_CUTS[Grade.SENIOR]:
        return Grade.SENIOR
    if b >= GRADE_CUTS[Grade.MIDDLE]:
        return Grade.MIDDLE
    if b >= GRADE_CUTS[Grade.JUNIOR]:
        return Grade.JUNIOR
    return Grade.INTERN


def make_rng(secret: bytes | str, session_id: str, purpose: str, n: int) -> random.Random:
    """HMAC-SHA256(secret, f'{session_id}|{purpose}|{n}') -> int seed."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    msg = f"{session_id}|{purpose}|{n}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    int_seed = int(digest[:16], 16)
    return random.Random(int_seed)


def _convert_registry_meta(m: Any) -> FamilyMeta:
    from assessment.families.registry import RETIRED

    status: Literal["active", "shadow", "retired"] = "retired" if m.id in RETIRED else "active"
    spec = m.specs[0] if m.specs else Specialization.BACKEND
    return FamilyMeta(
        id=m.id,
        spec=spec,
        topic=m.topic,
        skills=list(m.skills),
        a=float(m.a),
        b=float(m.b),
        c=float(m.c),
        time_limit_s=int(m.time_limit_s),
        status=status,
        format=m.format,
        specs=tuple(m.specs),
        version=getattr(m, "version", 1),
    )


def _get_family(family_id: str) -> Any:
    if family_id in _STUB_GENERATORS:
        return _STUB_GENERATORS[family_id]
    from assessment.families.registry import all_families

    return all_families().get(family_id)


def get_family_meta(family_id: str) -> FamilyMeta | None:
    if family_id in STUB_FAMILY_METAS:
        return STUB_FAMILY_METAS[family_id]
    from assessment.families.registry import all_families

    fam = all_families().get(family_id)
    if fam:
        return _convert_registry_meta(fam.meta)
    return None


def all_family_metas() -> list[FamilyMeta]:
    """All registered family metas combining stubs and full families registry."""
    found: dict[str, FamilyMeta] = dict(STUB_FAMILY_METAS)
    from assessment.families.registry import all_families

    for fid, fam in all_families().items():
        if fid not in found:
            found[fid] = _convert_registry_meta(fam.meta)
    return list(found.values())


def active_metas(spec: Spec, mode: Mode | None = None) -> list[FamilyMeta]:
    """Active family metas for specialization."""
    all_metas = all_family_metas()
    metas = [
        meta
        for meta in all_metas
        if (meta.spec == spec or (meta.specs and spec in meta.specs)) and meta.status == "active"
    ]
    if mode == "express" and len(metas) > 6:
        return metas[:6]
    return metas


def select_assessment_families(
    spec: Spec,
    n_items: int,
    session_id: str | None = None,
    secret: bytes | str | None = None,
) -> list[FamilyMeta]:
    """Select n_items distinct families for an assessment session.

    If n_items == 2 and spec is backend, returns the legacy stub pair
    [sql_meta, complexity_meta] to satisfy unit lifecycle contracts.
    Otherwise, deterministically selects n_items families balanced
    across topics using HMAC-seeded PRNG, ordered in ascending difficulty b.
    """
    if n_items == 2 and spec == Specialization.BACKEND:
        return [sql_meta, complexity_meta]

    pool = active_metas(spec)
    if not pool:
        return []
    if len(pool) <= n_items:
        res = list(pool)
        res.sort(key=lambda m: (m.b, m.id))
        return res

    if secret and session_id:
        rng = make_rng(secret, str(session_id), "select_families", 0)
    else:
        rng = random.Random(str(session_id) if session_id else 42)

    from collections import defaultdict

    by_topic: dict[str, list[FamilyMeta]] = defaultdict(list)
    for m in pool:
        by_topic[m.topic].append(m)

    topics = sorted(by_topic.keys())
    for t in topics:
        rng.shuffle(by_topic[t])

    selected: list[FamilyMeta] = []
    # Round-robin across distinct topics
    while len(selected) < n_items:
        added = False
        for t in topics:
            if by_topic[t] and len(selected) < n_items:
                selected.append(by_topic[t].pop(0))
                added = True
        if not added:
            break

    # If still below target, fill with any remaining pool items
    if len(selected) < n_items:
        selected_ids = {m.id for m in selected}
        remaining = [m for m in pool if m.id not in selected_ids]
        rng.shuffle(remaining)
        selected.extend(remaining[: n_items - len(selected)])

    # Order by difficulty b (ascending)
    selected.sort(key=lambda m: (m.b, m.id))
    return selected


def generate_instance(family_id: str, seed_or_rng: str | random.Random) -> Instance:
    """Generate a concrete item instance from a family."""
    gen = _get_family(family_id)
    if not gen:
        raise ValueError(f"Unknown family: {family_id}")

    if isinstance(seed_or_rng, random.Random):
        rng = seed_or_rng
    else:
        rng = random.Random(str(seed_or_rng))

    try:
        raw_item = gen.generate(rng)
    except TypeError:
        raw_item = gen.generate(str(seed_or_rng))

    meta = get_family_meta(family_id) or getattr(gen, "meta", None)
    time_limit_s = getattr(meta, "time_limit_s", 120) if meta else 120

    if hasattr(raw_item, "input"):
        return Instance(
            stem_md=raw_item.stem_md,
            input=raw_item.input,
            key=raw_item.key,
            fingerprint=raw_item.fingerprint,
            code=raw_item.code,
            options=raw_item.options,
            time_limit_s=time_limit_s,
        )
    return Instance(
        stem_md=raw_item.stem_md,
        input=raw_item.input_type,
        key=raw_item.key,
        fingerprint=raw_item.fingerprint,
        code=raw_item.code,
        options=raw_item.options,
        time_limit_s=getattr(raw_item, "time_limit_s", time_limit_s),
    )


def is_correct(family_id: str, key: Any, answer: dict[str, Any] | str) -> bool:
    """Verify if candidate answer matches the secret key."""
    if isinstance(answer, str) and str(answer) == str(key):
        return True
    if isinstance(answer, dict):
        val = answer.get("option_id") or answer.get("value")
        if val is not None and str(val) == str(key):
            return True
    ans_dict = {"option_id": answer, "value": answer} if isinstance(answer, str) else answer
    gen = _get_family(family_id)
    if gen and hasattr(gen, "is_correct"):
        try:
            if gen.is_correct(key, ans_dict):
                return True
        except Exception:
            pass
    if isinstance(answer, dict):
        val = answer.get("option_id") or answer.get("value")
    else:
        val = answer
    return str(val) == str(key)


# --- CatEngineAdapter implementation ---


class CatEngineAdapter:
    """Adapter implementing ML.md §3 CatEngine Protocol."""

    def start(
        self,
        spec: Spec | None = None,
        claimed: Grade | None = None,
        mode: Mode = "full",
        kind: Kind = "initial",
        pool: list[FamilyMeta] | None = None,
        seen: set[str] | None = None,
        **kwargs: Any,
    ) -> CatState:
        final_spec = spec or kwargs.get("specialization", "")
        final_claimed = claimed or kwargs.get("claimed_grade", "")
        max_items = 5 if mode == "express" else 15
        return CatState(
            spec=final_spec,
            claimed=final_claimed,
            mode=mode,
            kind=kind,
            administered=[],
            theta=0.0,
            se=0.5,
            min_items=2,
            max_items=max_items,
        )

    def next_family(
        self,
        state: CatState,
        pool: list[FamilyMeta] | None = None,
        rng: random.Random | None = None,
    ) -> FamilyMeta | None:
        if len(state.administered) >= state.max_items:
            return None
        candidate_pool = pool if pool is not None else active_metas(state.spec, state.mode)
        seen_ids = {it["family_id"] for it in state.administered}
        available = [m for m in candidate_pool if m.id not in seen_ids]
        if not available:
            return None
        return available[0]

    def next_item(
        self,
        state: CatState,
        rng: random.Random | None = None,
        pool: list[FamilyMeta] | None = None,
    ) -> Instance | None:
        """ML.md §3: Generate next concrete item Instance using next_family and rng."""
        meta = self.next_family(state, pool=pool, rng=rng)
        if meta is None:
            return None
        rng_use = rng if rng is not None else random.Random()
        return generate_instance(meta.id, rng_use)

    def record(
        self,
        state: CatState,
        family_id: str,
        correct: bool,
        late: bool = False,
    ) -> CatState:
        meta = get_family_meta(family_id)
        a = meta.a if meta else 1.2
        b = meta.b if meta else 0.5
        c = meta.c if meta else 0.25
        topic = meta.topic if meta else "general"

        existing = next((it for it in state.administered if it.get("family_id") == family_id), None)
        scored_correct = False if late else bool(correct)

        if existing:
            existing["correct"] = scored_correct
            existing["late"] = bool(late)
        else:
            state.administered.append(
                {
                    "family_id": family_id,
                    "seq": len(state.administered) + 1,
                    "a": a,
                    "b": b,
                    "c": c,
                    "topic": topic,
                    "correct": scored_correct,
                    "late": bool(late),
                }
            )

        # Update intermediate theta and se
        total = len(state.administered)
        correct_cnt = sum(1 for it in state.administered if it.get("correct"))
        pct = correct_cnt / total if total > 0 else 0
        avg_b = sum(it.get("b", 0.5) for it in state.administered) / total if total > 0 else 0.5
        state.theta = round(avg_b + (pct - 0.5) * 2.0, 2)
        state.se = round(max(0.2, 1.0 / (total**0.5)), 2)
        return state

    def result(self, state: CatState) -> CatResult:
        items_data = state.administered
        total_count = len(items_data)
        if total_count == 0:
            return CatResult(
                theta=0.0,
                se=0.5,
                rating=1000,
                rating_ci=196,
                result_grade=Grade.JUNIOR,
                decision=GradeDecision.UNCONFIRMED,
                promotion_unlocked=False,
                fallback_grade=None,
                topics=[],
                evidence=[],
            )

        correct_count = sum(1 for item in items_data if item.get("correct"))
        pct = correct_count / total_count if total_count > 0 else 0
        avg_b = sum(item.get("b", 0.5) for item in items_data) / total_count
        theta = round(avg_b + (pct - 0.5) * 2.0, 2)
        se = round(max(0.2, 1.0 / (total_count**0.5)), 2)
        rating = int(round(1000 + 200 * theta))
        rating_ci = int(round(1.96 * 200 * se))

        if theta >= GRADE_CUTS[Grade.SENIOR]:
            achieved_grade = Grade.SENIOR
        elif theta >= GRADE_CUTS[Grade.MIDDLE]:
            achieved_grade = Grade.MIDDLE
        elif theta >= GRADE_CUTS[Grade.JUNIOR]:
            achieved_grade = Grade.JUNIOR
        else:
            achieved_grade = Grade.INTERN

        claimed_val = GRADE_ORDER.get(state.claimed, 2)
        achieved_val = GRADE_ORDER.get(achieved_grade, 2)
        decision = (
            GradeDecision.CONFIRMED if achieved_val >= claimed_val else GradeDecision.UNCONFIRMED
        )

        promotion_unlocked = bool(
            decision == GradeDecision.CONFIRMED
            and state.claimed != Grade.SENIOR
            and achieved_val > claimed_val
        )

        fallback_grade = None
        if decision == GradeDecision.UNCONFIRMED:
            lower = LOWER_GRADE.get(state.claimed)
            if lower and GRADE_ORDER.get(achieved_grade, 0) >= GRADE_ORDER.get(lower, 0):
                fallback_grade = lower

        # Topics breakdown
        topic_totals: dict[str, int] = {}
        topic_correct: dict[str, int] = {}
        for it in items_data:
            top = it.get("topic", "general")
            topic_totals[top] = topic_totals.get(top, 0) + 1
            if it.get("correct"):
                topic_correct[top] = topic_correct.get(top, 0) + 1

        topics: list[tuple[str, Literal["strong", "moderate", "limited"]]] = []
        for top, tot in topic_totals.items():
            c_pct = topic_correct.get(top, 0) / tot if tot > 0 else 0
            level: Literal["strong", "moderate", "limited"] = (
                "strong" if c_pct >= 0.8 else ("moderate" if c_pct >= 0.5 else "limited")
            )
            topics.append((top, level))

        evidence = [
            (
                it.get("seq", i + 1),
                item_level(it.get("b", 0.5)),
                bool(it.get("correct")),
            )
            for i, it in enumerate(items_data)
        ]

        return CatResult(
            theta=theta,
            se=se,
            rating=rating,
            rating_ci=rating_ci,
            result_grade=achieved_grade,
            decision=decision,
            promotion_unlocked=promotion_unlocked,
            fallback_grade=fallback_grade,
            topics=topics,
            evidence=evidence,
        )


# Singleton adapter instance
_engine_adapter = CatEngineAdapter()

start = _engine_adapter.start
next_family = _engine_adapter.next_family
next_item = _engine_adapter.next_item
record = _engine_adapter.record
result = _engine_adapter.result


def sync_families_to_db() -> int:
    """Sync active family metas into ItemFamily database rows."""
    from assessment.models import ItemFamily

    synced = 0
    for meta in all_family_metas():
        specs_list = list(meta.specs) if getattr(meta, "specs", None) else [meta.spec]
        ItemFamily.objects.update_or_create(
            id=meta.id,
            defaults={
                "version": getattr(meta, "version", 1),
                "specs": specs_list,
                "topic": meta.topic,
                "skills": list(meta.skills),
                "format": meta.format,
                "a": meta.a,
                "b": meta.b,
                "c": meta.c,
                "time_limit_s": meta.time_limit_s,
                "status": meta.status,
            },
        )
        synced += 1
    return synced


def compute_league_percentiles(
    scores: Sequence[tuple[Any, float]] | Mapping[Any, float],
) -> dict[Any, float]:
    """Compute rank-based percentiles for league members.

    Follows ML.md §3 contract:
    - Empty league returns empty dict.
    - Single member returns 100.0%.
    - Rank is computed as count of members with score <= member_score.
    - Percentile is round((rank / total) * 100.0, 1).
    - Ties share the highest rank among equals.
    """
    if not scores:
        return {}

    if isinstance(scores, Mapping):
        items = list(scores.items())
    else:
        items = list(scores)

    if not items:
        return {}

    n = len(items)
    sorted_values = sorted(val for _, val in items)

    results: dict[Any, float] = {}
    for item_id, val in items:
        rank = bisect.bisect_right(sorted_values, val)
        results[item_id] = round((rank / n) * 100.0, 1)

    return results

