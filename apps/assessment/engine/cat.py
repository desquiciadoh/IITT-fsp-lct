"""CAT contract (ML.md §3): session state, result, engine protocol.

ML-0 ships `StubCatEngine` so BE can wire the final shapes; ML-3 replaces it with the
3PL/EAP engine behind the same signatures.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..families.base import GRADES, FamilyMeta, Grade, Spec
from .content import load_content

Mode = Literal["full", "express"]
Kind = Literal["initial", "fallback", "promotion", "screening"]
TopicLevel = Literal["strong", "moderate", "limited"]

MODES: tuple[str, ...] = ("full", "express")
KINDS: tuple[str, ...] = ("initial", "fallback", "promotion", "screening")


STATE_VERSION = 1   # bump only with a from_json migration; new fields are optional and read with .get


@dataclass
class CatState:
    spec: Spec
    claimed: Grade
    mode: Mode
    kind: Kind
    administered: list[dict]   # [{family_id, seq, a, b, c, topic, correct: bool|None, late: bool}]
    theta: float
    se: float
    min_items: int
    max_items: int
    seen: list[str] = field(default_factory=list)   # family ids from earlier attempts, sorted
    blueprint: list[tuple[str, float]] | None = None  # screening quotas; None -> the spec blueprint

    def to_json(self) -> dict:
        """Plain JSON types only; BE stores it in AssessmentSession.state (JSONB)."""
        return {
            "v": STATE_VERSION, "spec": self.spec, "claimed": self.claimed, "mode": self.mode, "kind": self.kind,
            "administered": [dict(x) for x in self.administered],
            "theta": float(self.theta), "se": float(self.se),
            "min_items": int(self.min_items), "max_items": int(self.max_items),
            "seen": list(self.seen),
            "blueprint": [[t, float(w)] for t, w in self.blueprint] if self.blueprint is not None else None,
        }

    @classmethod
    def from_json(cls, d: dict) -> CatState:
        if d.get("v", 1) > STATE_VERSION:
            raise ValueError(f"CatState v{d['v']} is newer than this engine (v{STATE_VERSION})")
        bp = d.get("blueprint")
        return cls(
            spec=d["spec"], claimed=d["claimed"], mode=d["mode"], kind=d["kind"],
            administered=[dict(x) for x in d["administered"]],
            theta=float(d["theta"]), se=float(d["se"]),
            min_items=int(d["min_items"]), max_items=int(d["max_items"]),
            seen=list(d.get("seen", [])),
            blueprint=[(str(t), float(w)) for t, w in bp] if bp is not None else None,
        )


@dataclass(frozen=True)
class CatResult:
    theta: float
    se: float
    rating: int                     # round(1000 + 200·θ)
    rating_ci: int                  # round(1.96 · 200 · SE)
    result_grade: Grade
    decision: Literal["confirmed", "unconfirmed"]
    promotion_unlocked: bool        # P(θ ≥ next cut) ≥ 0.9
    fallback_grade: Grade | None    # highest lower grade with P(θ ≥ cut) ≥ 0.8, else None
    topics: list[tuple[str, TopicLevel]]
    evidence: list[tuple[int, Grade, bool]]     # (seq, item level, correct)


class CatEngine(Protocol):
    """Session protocol. Semantics BE relies on:

    - `next_family` appends a pending entry (correct=None) to `state.administered` and returns
      its meta; called again before `record`, it returns the same family (safe to retry). BE
      generates the item with make_rng(secret, session_id, family_id, n=seq) and persists state.
    - `record` scores the pending entry; `late=True` scores it as incorrect.
    - `result` scores any entry still pending as incorrect (a served item that was never
      answered counts against the candidate, so ending a session can't skip a hard item).
    - `blueprint` (screening only) replaces the spec blueprint's topic quotas; it never
      changes how θ is scored.
    """

    def start(self, spec: Spec, claimed: Grade, mode: Mode, kind: Kind,
              pool: list[FamilyMeta], seen: set[str],
              blueprint: list[tuple[str, float]] | None = None) -> CatState: ...

    def next_family(self, state: CatState, pool: list[FamilyMeta],
                    rng: random.Random) -> FamilyMeta | None: ...      # None -> stop

    def record(self, state: CatState, family_id: str, correct: bool,
               late: bool = False) -> CatState: ...                     # late -> scored as incorrect

    def result(self, state: CatState) -> CatResult: ...


def band_of(theta: float, cuts: tuple[float, float, float] | None = None) -> Grade:
    """Grade band of a point on the θ scale; cuts between intern|junior|middle|senior from grades.yaml."""
    cuts = cuts if cuts is not None else load_content().band_cuts
    return GRADES[sum(theta >= x for x in cuts)]  # type: ignore[return-value]


def item_level(meta: FamilyMeta) -> Grade:
    """Difficulty band of b -> ItemView.level."""
    return band_of(meta.b)


class StubCatEngine:
    """ML-0 stub: 8 items in id order, θ = (correct − 4) / 2, decision against the claimed cut."""

    N_ITEMS = 8

    def start(self, spec, claimed, mode, kind, pool, seen, blueprint=None) -> CatState:
        return CatState(spec=spec, claimed=claimed, mode=mode, kind=kind, administered=[],
                        theta=0.0, se=1.0, min_items=self.N_ITEMS, max_items=self.N_ITEMS,
                        seen=sorted(seen), blueprint=list(blueprint) if blueprint is not None else None)

    def next_family(self, state, pool, rng) -> FamilyMeta | None:
        pending = [x for x in state.administered if x["correct"] is None]
        by_id = {m.id: m for m in pool}
        if pending:
            return by_id.get(pending[-1]["family_id"])
        if len(state.administered) >= state.max_items:
            return None
        used = {x["family_id"] for x in state.administered}
        free = sorted((m for m in pool if m.id not in used), key=lambda m: (m.id in state.seen, m.id))
        if not free:
            return None
        meta = free[0]
        state.administered.append({"family_id": meta.id, "seq": len(state.administered) + 1,
                                   "a": meta.a, "b": meta.b, "c": meta.c, "topic": meta.topic,
                                   "correct": None, "late": False})
        return meta

    def record(self, state, family_id, correct, late=False) -> CatState:
        for x in state.administered:
            if x["family_id"] == family_id and x["correct"] is None:
                x["correct"] = bool(correct) and not late
                x["late"] = bool(late)
                break
        else:
            raise ValueError(f"family {family_id!r} is not pending in this session")
        n_correct = sum(1 for x in state.administered if x["correct"])
        state.theta = (n_correct - 4) / 2
        state.se = 0.5
        return state

    def result(self, state) -> CatResult:
        for x in state.administered:
            if x["correct"] is None:          # served, never answered: incorrect
                x["correct"], x["late"] = False, True
        state.theta = (sum(1 for x in state.administered if x["correct"]) - 4) / 2
        theta, se = state.theta, state.se
        grade = band_of(theta)
        cut = load_content().grade(state.claimed).theta_cut
        answered = [x for x in state.administered if x["correct"] is not None]
        return CatResult(
            theta=theta, se=se, rating=round(1000 + 200 * theta), rating_ci=round(1.96 * 200 * se),
            result_grade=grade, decision="confirmed" if theta >= cut else "unconfirmed",
            promotion_unlocked=False, fallback_grade=None,
            topics=sorted({(x["topic"], "moderate") for x in answered}),
            evidence=[(x["seq"], band_of(x["b"]), bool(x["correct"])) for x in answered],
        )
