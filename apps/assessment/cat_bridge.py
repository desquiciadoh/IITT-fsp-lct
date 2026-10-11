"""Bridge between the Django assessment service and the ML CAT engine (N2).

Exposes the same module-level API as ``assessment.engine_adapter`` (start /
record / result / CatState) but is backed by the real ``IrtCatEngine`` and the
real family registry (``assessment.families.registry``), so:

- theta/se come from EAP on the fixed-c 3PL model (ML.md §3);
- stop rules (express/max_items/se/ci/pool_exhausted) drive session length;
- pending items (correct=None) are supported, matching the engine protocol.

Legacy states without a version field (written by ``engine_adapter.CatState``,
which never persisted ``v``) are migrated losslessly: every administered entry
already carries a concrete bool ``correct``, so no entry becomes pending and
the recorded theta/se are simply re-derived from the item responses (EAP is a
pure function of the responses).
"""

from __future__ import annotations

import random
from typing import Any

from django.conf import settings

from assessment.engine.cat import (
    STATE_VERSION,
    CatResult,
    CatState,
    IrtCatEngine,
)
from assessment.engine.cat import item_level as _ml_item_level
from assessment.engine.content import load_content
from assessment.families.base import FamilyMeta as RegistryFamilyMeta
from assessment.families.registry import all_families
from assessment.families.registry import active_metas as registry_active_metas
from assessment.families.registry import make_rng as registry_make_rng

ENGINE = IrtCatEngine(content=load_content())

__all__ = [
    "ENGINE",
    "CatResult",
    "CatState",
    "STATE_VERSION",
    "active_metas",
    "all_family_metas",
    "family_meta",
    "generate_instance",
    "grade_cut",
    "is_correct",
    "item_level",
    "make_rng",
    "next_family",
    "record",
    "result",
    "seed_secret",
    "start",
    "sync_families_to_db",
]


def seed_secret() -> bytes:
    secret = getattr(settings, "ITEM_SEED_SECRET", "") or ""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not secret:
        raise ValueError("ITEM_SEED_SECRET is not configured")
    return secret


def make_rng(session_id, purpose: str, n: int) -> random.Random:
    """HMAC-seeded rng per ML.md §3 (registry.make_rng with the Django secret)."""
    return registry_make_rng(seed_secret(), str(session_id), purpose, n)


def grade_cut(grade: str) -> float:
    """theta cut of a grade from the authoritative content/grades.yaml."""
    return ENGINE.content.grade(grade).theta_cut


def _is_legacy_state(d: dict) -> bool:
    """True for adapter-written states (no ``v`` field)."""
    return "v" not in d


def normalize_state_dict(d: dict) -> dict:
    """Return an engine-readable state dict (adds ``v`` and optional fields)."""
    if not isinstance(d, dict):
        raise ValueError(f"session state must be a dict, got {type(d).__name__}")
    if not _is_legacy_state(d):
        return d
    out = dict(d)
    out["v"] = STATE_VERSION
    out.setdefault("seen", [])
    out.setdefault("blueprint", None)
    out.setdefault("stop_reason", None)
    # Legacy entries always have a concrete bool; make sure none is missing.
    admin = []
    for x in out.get("administered", []):
        y = dict(x)
        if "correct" not in y or y["correct"] is None:
            y["correct"] = False
        y.setdefault("late", False)
        admin.append(y)
    out["administered"] = admin
    return out


def load_state(raw: Any) -> CatState | None:
    """Parse AssessmentSession.state into an engine CatState (None if unusable)."""
    if not raw:
        return None
    try:
        return CatState.from_json(normalize_state_dict(raw))
    except Exception:
        return None


# --- registry helpers -------------------------------------------------------

_REGISTRY = None


def _registry() -> dict[str, RegistryFamilyMeta]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = all_families()
    return _REGISTRY


def family_meta(family_id: str) -> RegistryFamilyMeta:
    fam = _registry().get(family_id)
    if fam is None:
        raise ValueError(f"unknown family: {family_id!r}")
    return fam


def active_metas(spec: str) -> list[RegistryFamilyMeta]:
    """Active (non-retired) registry metas serving `spec`."""
    return registry_active_metas(spec)


def all_family_metas() -> list[RegistryFamilyMeta]:
    """Every registered family meta, retired ones included."""
    return [fam.meta for fam in _registry().values()]


def item_level(meta_or_b):
    b = meta_or_b.b if hasattr(meta_or_b, "b") else float(meta_or_b)
    return _ml_item_level(b)  # type: ignore[arg-type]


def generate_instance(family_id: str, rng: random.Random):
    """Render an item instance with the given rng (registry families)."""
    return family_meta(family_id).generate(rng)


def is_correct(family_id: str, key: Any, answer: Any) -> bool:
    """Grade an answer through the owning family's typed checker.

    ``answer`` may be a bare string (option id or typed value) or a dict;
    it is routed into the family protocol shape {"option_id": ...} |
    {"value": ...} so number/text checkers don't accidentally compare
    against the option-id slot.
    """
    fam = _registry().get(family_id)
    if fam is not None:
        if isinstance(answer, str):
            payload: dict = {"value": answer}
        elif isinstance(answer, dict):
            payload = answer
        else:
            payload = {"value": str(answer)}
        try:
            return bool(fam.is_correct(key, payload))
        except Exception:
            return False
    # Unknown family (should not happen): conservative string compare.
    if isinstance(answer, dict):
        val = answer.get("option_id") or answer.get("value")
    else:
        val = answer
    return str(val) == str(key)


def grade_answer(item, answer_val: str) -> bool:
    """Type-aware grading of a submitted answer for a served AssessmentItem.

    The API sends the candidate's pick either as ``option_id`` (choice items)
    or as ``value`` (number/text items); views collapse both into one string.
    Reconstruct the protocol payload from the item's rendered input kind so
    the family's typed checker receives the right slot.
    """
    view = item.view or {}
    payload: dict
    if view.get("options") and any(o.get("id") == answer_val for o in view["options"]):
        payload = {"option_id": answer_val}
    else:
        payload = {"value": answer_val}
    fam = _registry().get(item.family_id)
    if fam is not None:
        try:
            return bool(fam.is_correct(item.key, payload))
        except Exception:
            return False
    val = payload.get("option_id") or payload.get("value")
    return str(val) == str(item.key)


# --- CatEngine facade (same call shapes as engine_adapter) ------------------


def start(
    spec=None,
    claimed=None,
    mode="full",
    kind="initial",
    pool=None,
    seen=None,
    blueprint=None,
    test_mode=None,
    **kwargs: Any,
) -> CatState:
    """Start an engine session.

    ``mode`` is the *business* mode (AssessmentMode: full | express — stored on
    the session and shown to FE).  ``test_mode`` optionally overrides the
    engine-protocol stop-rule window ("full"|"express") for rebuild/replay
    paths that must be able to append more entries than the real session's
    window allows; it defaults to ``mode``.
    """
    final_spec = spec or kwargs.get("specialization", "")
    final_claimed = claimed or kwargs.get("claimed_grade", "")
    return ENGINE.start(
        spec=final_spec,
        claimed=final_claimed,
        mode=test_mode or mode,
        kind=kind,
        pool=pool if pool is not None else active_metas(final_spec),
        seen=set(seen or ()),
        blueprint=blueprint,
    )


def next_family(state: CatState, pool=None, rng=None):
    return ENGINE.next_family(
        state,
        pool if pool is not None else active_metas(state.spec),
        rng if rng is not None else random.Random(),
    )


def record(
    state: CatState,
    family_id: str,
    correct: bool,
    late: bool = False,
    *,
    params: dict | None = None,
) -> CatState:
    """Score the pending entry of `family_id` through the real engine.

    ``params`` (optional dict with a/b/topic) overrides the values stored on
    the pending entry — replay paths (finalize recovery, fallback rebuild)
    must grade with the *served* item parameters persisted on AssessmentItem,
    which can differ from the current registry meta after a re-calibration.
    """
    # Replaying a response for an already-scored entry (legacy rebuild paths)
    # must not blow up: reset the LAST scored entry of this family to pending
    # so the engine's record() finds it (duplicate families are replayed in
    # order; the last one is always the one being re-graded).
    pending = None
    for x in state.administered:
        if x["family_id"] == family_id and x["correct"] is None:
            pending = x
            break
    if pending is None:
        for x in reversed(state.administered):
            if x["family_id"] == family_id:
                x["correct"] = None
                pending = x
                break
    if pending is not None and params:
        for k in ("a", "b", "topic"):
            if params.get(k) is not None:
                pending[k] = params[k]
    # Rebuild/replay paths (fallback eligibility, finalize recovery) append
    # every answered item onto a fresh state; the engine's stop rules would
    # otherwise freeze the administered list once the window is reached.
    # Relax the window so all replayed entries are scored by EAP.
    if not any(x["correct"] is None for x in state.administered):
        state.max_items = max(state.max_items, len(state.administered) + 1)
    return ENGINE.record(state, family_id, correct, late)


def replay_session(session, *, relax_window: bool = True) -> "CatState":
    """Rebuild an engine state by replaying a session's answered items.

    Uses the parameters persisted on each AssessmentItem (via ``record``'s
    ``params`` override) so theta/se are derived exactly as during the live
    test. Unanswered (pending) items are skipped. When ``relax_window`` is
    set, the stop-rule window is widened so every replayed entry is scored
    (replay appends onto a fresh state whose max_items may be smaller than
    the number of served items, e.g. express sessions finished via /finish).
    """
    state = start(
        spec=session.specialization,
        claimed=session.claimed_grade,
        mode=session.mode,
        kind=session.kind,
    )
    if relax_window:
        state.max_items = max(state.max_items, session.items.count() + 5)
    for it in session.items.order_by("seq"):
        if it.answered_at is None:
            continue
        late = bool(isinstance(it.answer, dict) and it.answer.get("late"))
        state = record(
            state,
            it.family_id,
            correct=bool(it.correct),
            late=late,
            params={"a": it.family.a, "b": it.family.b, "topic": it.family.topic},
        )
    return state


def result(state: CatState) -> CatResult:
    return ENGINE.result(state)


def sync_families_to_db() -> int:
    """Upsert every registered family (ML-1) into ItemFamily rows.

    Families in registry.RETIRED are stored with status='retired' so they can
    still re-grade old instances but are never selected (active_metas excludes
    them). Returns the number of synced rows.
    """
    from assessment.families.registry import RETIRED
    from assessment.models import ItemFamily

    synced = 0
    for fid, fam in _registry().items():
        meta = fam.meta
        ItemFamily.objects.update_or_create(
            id=fid,
            defaults={
                "version": meta.version,
                "specs": list(meta.specs),
                "topic": meta.topic,
                "skills": list(meta.skills),
                "format": meta.format,
                "a": meta.a,
                "b": meta.b,
                "c": meta.c,
                "time_limit_s": meta.time_limit_s,
                "status": "retired" if fid in RETIRED else "active",
            },
        )
        synced += 1
    return synced
