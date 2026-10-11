"""CAT (ML-3): session state, result, engine protocol and the fixed-c 3PL engine.

IrtCatEngine
  start        empty state; θ̂ = 0 and SE = the prior SD.
  next_family  checks the stop rules, then picks the most informative eligible family and draws
               uniformly among the top 5 (randomesque exposure control) with the passed rng.
               A family is eligible if it serves the session's spec, was not administered in this
               session, and its topic is under its blueprint quota (count < ⌊w·(n+1)⌋ + 1, so a
               topic never runs more than one item ahead of its proportional share); topics behind
               their share go first: only topics within 0.5 of the largest deficit w·(n+1) − count
               compete (Kingsbury-Zara with slack), so quotas act as floors too. Families unseen
               in earlier attempts are preferred. The first item is targeted at start_theta(claimed),
               later ones at the current θ̂. Ties break by family id.
  record       scores the pending item (late -> incorrect) and re-estimates θ̂, SE (EAP, neutral prior).
  result       grade policy on the same posterior (policy.decide), topic evidence, item evidence.
Stop rules: express mode stops at 8 items. Full mode stops at 20 items, or at >= 10 once
SE <= 0.30 or the 95 % CI θ̂ ± 1.96·SE lies wholly above or below cut(claimed). It also stops
when no family is left. A session counts as complete (and may confirm a grade) only if a stop
rule ended it; a session BE ends early (finish, abandon) is scored but never confirms (D8).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..families.base import GRADES, SPECS, FamilyMeta, Grade, Spec
from .content import Content, load_content
from .irt import eap, information, posterior
from .policy import band_of, decide
from .topics import topic_levels

Mode = Literal["full", "express"]
Kind = Literal["initial", "fallback", "promotion", "screening"]
TopicLevel = Literal["strong", "moderate", "limited"]

MODES: tuple[str, ...] = ("full", "express")
KINDS: tuple[str, ...] = ("initial", "fallback", "promotion", "screening")

DEFICIT_SLACK = 0.5  # topics within half an item of the largest deficit compete on information

STATE_VERSION = 1   # bump only with a from_json migration; new fields are optional and read with .get

__all__ = ["CatEngine", "CatResult", "CatState", "IrtCatEngine", "band_of", "item_level"]


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
    stop_reason: str | None = None                    # set when a stop rule ends the test

    def to_json(self) -> dict:
        """Plain JSON types only; BE stores it in AssessmentSession.state (JSONB)."""
        return {
            "v": STATE_VERSION, "spec": self.spec, "claimed": self.claimed, "mode": self.mode, "kind": self.kind,
            "administered": [dict(x) for x in self.administered],
            "theta": float(self.theta), "se": float(self.se),
            "min_items": int(self.min_items), "max_items": int(self.max_items),
            "seen": list(self.seen),
            "blueprint": [[t, float(w)] for t, w in self.blueprint] if self.blueprint is not None else None,
            "stop_reason": self.stop_reason,
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
            stop_reason=d.get("stop_reason"),
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
    complete: bool = False          # a stop rule ended the test (D8); False -> never confirmed
    stop_reason: str | None = None  # express | max_items | se | ci | pool_exhausted | None


class CatEngine(Protocol):
    """Session protocol. Semantics BE relies on:

    - `next_family` appends a pending entry (correct=None) to `state.administered` and returns
      its meta; called again before `record`, it returns the same family (safe to retry). BE
      generates the item with make_rng(secret, session_id, family_id, n=seq), selects with
      make_rng(secret, session_id, "select", n=seq), and persists state.
    - `record` scores the pending entry; `late=True` scores it as incorrect.
    - `result` scores any entry still pending as incorrect (a served item that was never
      answered counts against the candidate, so ending a session can't skip a hard item). It
      works on a copy and never changes `state`; it applies the stop rules itself, so calling it
      right after the last `record` gives the same answer as after `next_family` returns None.
    - A pending family that left the pool (retired mid-session) is looked up in the registry,
      so the session can finish; `next_family` never selects it again.
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


def item_level(meta: FamilyMeta) -> Grade:
    """Difficulty band of b -> ItemView.level."""
    return band_of(meta.b)  # type: ignore[return-value]


class IrtCatEngine:
    TOP_K = 5
    FULL_MIN, FULL_MAX, EXPRESS = 10, 20, 8
    SE_STOP = 0.30
    Z95 = 1.96

    def __init__(self, content: Content | None = None):
        self.content = content or load_content()

    # ── protocol ──────────────────────────────────────────────────────────
    def start(self, spec, claimed, mode, kind, pool, seen, blueprint=None) -> CatState:
        if spec not in SPECS or claimed not in GRADES or mode not in MODES or kind not in KINDS:
            raise ValueError(f"bad session parameters: {spec!r}, {claimed!r}, {mode!r}, {kind!r}")
        lo, hi = (self.EXPRESS, self.EXPRESS) if mode == "express" else (self.FULL_MIN, self.FULL_MAX)
        theta, se = eap([], [])
        return CatState(spec=spec, claimed=claimed, mode=mode, kind=kind, administered=[],
                        theta=theta, se=se, min_items=lo, max_items=hi, seen=sorted(set(seen)),
                        blueprint=self._normalised(blueprint, spec) if blueprint is not None else None)

    def next_family(self, state, pool, rng) -> FamilyMeta | None:
        by_id = {m.id: m for m in pool}
        pending = [x for x in state.administered if x["correct"] is None]
        if pending:
            fid = pending[-1]["family_id"]
            meta = by_id.get(fid)
            if meta is None:                  # retired while pending: finish it from the registry
                from ..families.registry import all_families
                fam = all_families().get(fid)
                if fam is None:
                    raise ValueError(f"pending family {fid!r} is unknown")
                meta = fam.meta
            return meta
        if state.stop_reason is not None:
            return None
        reason = self.stop_rule(state)
        if reason is None:
            meta = self._select(state, pool, rng)
            if meta is not None:
                state.administered.append({"family_id": meta.id, "seq": len(state.administered) + 1,
                                           "a": float(meta.a), "b": float(meta.b), "c": float(meta.c),
                                           "topic": meta.topic, "correct": None, "late": False})
                return meta
            reason = "pool_exhausted"
        state.stop_reason = reason
        return None

    def record(self, state, family_id, correct, late=False) -> CatState:
        for x in state.administered:
            if x["family_id"] == family_id and x["correct"] is None:
                x["correct"] = bool(correct) and not late
                x["late"] = bool(late)
                break
        else:
            raise ValueError(f"family {family_id!r} is not pending in this session")
        state.theta, state.se = eap(*_responses(state.administered))
        return state

    def result(self, state) -> CatResult:
        st = CatState.from_json(state.to_json())          # never mutate the caller's state
        if st.stop_reason is None and not any(x["correct"] is None for x in st.administered):
            st.stop_reason = self.stop_rule(st)           # finished by the last record()
        for x in st.administered:
            if x["correct"] is None:                      # served, never answered: incorrect (D1)
                x["correct"], x["late"] = False, True
        items, resp = _responses(st.administered)
        post = posterior(items, resp)
        complete = self.is_complete(st)
        d = decide(post, st.claimed, complete, self.content)
        reference = st.claimed if d.decision == "confirmed" else d.result_grade
        return CatResult(
            theta=d.theta, se=d.se, rating=d.rating, rating_ci=d.rating_ci, result_grade=d.result_grade,
            decision=d.decision, promotion_unlocked=d.promotion_unlocked, fallback_grade=d.fallback_grade,
            topics=topic_levels(st.administered, reference, self.content),
            evidence=[(x["seq"], band_of(x["b"], self.content), bool(x["correct"]))
                      for x in st.administered],
            complete=complete, stop_reason=st.stop_reason)

    # ── rules ─────────────────────────────────────────────────────────────
    def stop_rule(self, state: CatState) -> str | None:
        """The stop rule that applies now, or None to continue."""
        n = len(state.administered)
        if state.mode == "express":
            return "express" if n >= self.EXPRESS else None
        if n >= state.max_items:
            return "max_items"
        if n < state.min_items:
            return None
        if state.se <= self.SE_STOP:
            return "se"
        cut = self.content.grade(state.claimed).theta_cut
        lo, hi = state.theta - self.Z95 * state.se, state.theta + self.Z95 * state.se
        if lo >= cut or hi < cut:
            return "ci"
        return None

    def _normalised(self, blueprint: list[tuple[str, float]], spec: str) -> list[tuple[str, float]]:
        """Screening quotas: topics of the spec only, duplicates merged, weights summing to 1."""
        allowed = set(self.content.topics_for(spec))
        merged: dict[str, float] = {}
        for t, w in blueprint:
            t, w = str(t), float(w)
            if t not in allowed:
                raise ValueError(f"blueprint topic {t!r} is not a {spec} topic")
            if w < 0 or not math.isfinite(w):
                raise ValueError(f"blueprint weight for {t!r} must be finite and >= 0")
            merged[t] = merged.get(t, 0.0) + w
        total = sum(merged.values())
        if total <= 0:
            raise ValueError("a screening blueprint needs at least one topic with a positive weight")
        return [(t, merged[t] / total) for t in sorted(merged) if merged[t] > 0]

    def is_complete(self, state: CatState) -> bool:
        """A stop rule ended the test; pool exhaustion counts only after min_items answers."""
        if state.stop_reason is None:
            return False
        if state.stop_reason == "pool_exhausted":
            return len(state.administered) >= state.min_items
        return True

    def _select(self, state: CatState, pool: list[FamilyMeta], rng: random.Random) -> FamilyMeta | None:
        used = {x["family_id"] for x in state.administered}
        cands = [m for m in pool if m.id not in used and state.spec in m.specs]
        if not cands:
            return None
        weights = dict(state.blueprint) if state.blueprint is not None else self.content.blueprints[state.spec]
        n = len(state.administered)
        counts: dict[str, int] = {}
        for x in state.administered:
            counts[x["topic"]] = counts.get(x["topic"], 0) + 1

        def under_quota(m: FamilyMeta) -> bool:
            w = weights.get(m.topic, 0.0)
            return w > 0 and counts.get(m.topic, 0) < math.floor(w * (n + 1)) + 1

        def deficit(m: FamilyMeta) -> float:
            return weights.get(m.topic, 0.0) * (n + 1) - counts.get(m.topic, 0)

        eligible = [m for m in cands if under_quota(m)]
        if eligible:                         # floor (Kingsbury-Zara): the most-behind topics compete
            top = max(deficit(m) for m in eligible)
            eligible = [m for m in eligible if deficit(m) >= top - DEFICIT_SLACK]
        if not eligible:                     # every quota is full or empty: any blueprint topic, else any
            eligible = [m for m in cands if weights.get(m.topic, 0.0) > 0] or cands
        unseen = [m for m in eligible if m.id not in state.seen]
        if unseen:
            eligible = unseen
        start = self.content.grade(state.claimed)
        if state.kind == "promotion" and state.claimed != GRADES[-1]:
            # promotion blueprint (ML-13): the test is about the next grade, so it starts at that
            # grade and keeps to items at least near its cut while any are left in the topic mix
            start = self.content.grade(GRADES[GRADES.index(state.claimed) + 1])
            hard = [m for m in eligible if m.b >= start.theta_cut + self.content.promotion_min_b_offset]
            if hard:
                eligible = hard
        target = start.start_theta if n == 0 else state.theta
        scored = sorted(((-float(information(target, m.a, m.b, m.c)), m.id, m) for m in eligible),
                        key=lambda t: (t[0], t[1]))
        top = [m for _, _, m in scored[: self.TOP_K]]
        return top[rng.randrange(len(top))]


def _responses(administered: list[dict]) -> tuple[list[tuple[float, float, float]], list[bool]]:
    answered = [x for x in administered if x["correct"] is not None]
    return ([(float(x["a"]), float(x["b"]), float(x["c"])) for x in answered],
            [bool(x["correct"]) for x in answered])



