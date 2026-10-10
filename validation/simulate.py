"""Simulated test-takers on the production CAT engine (shared by synth.py and sim_assessment.py).

A simulee with true ability θ answers each served family correctly with probability
P_true(θ) under that family's *true* item parameters, which differ from the nominal priors the
engine uses: a × U(0.8, 1.2) and b + N(0, 0.2) per family (ARCHITECTURE §2.12), drawn once per
world from its seed. This mimics imperfect calibration instead of testing the engine against
its own assumptions. Pure (no Django); imports the production engine, never a copy.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from assessment.engine.cat import CatResult, CatState, IrtCatEngine
from assessment.families.base import FamilyMeta
from assessment.families.registry import make_rng

SECRET = b"fsp-draft-validation"


@dataclass(frozen=True)
class TrueParams:
    a: float
    b: float
    c: float


def perturbed_params(metas: list[FamilyMeta], seed: int, a_jitter: float = 0.2, b_sd: float = 0.2,
                     ) -> dict[str, TrueParams]:
    """True item parameters per family: the prior perturbed once (deterministic per seed)."""
    rng = random.Random(f"true-params|{seed}")
    out = {}
    for m in sorted(metas, key=lambda m: m.id):
        out[m.id] = TrueParams(a=m.a * rng.uniform(1 - a_jitter, 1 + a_jitter), b=m.b + rng.gauss(0, b_sd), c=m.c)
    return out


def p_correct(theta: float, t: TrueParams) -> float:
    return t.c + (1 - t.c) / (1 + math.exp(-t.a * (theta - t.b)))


@dataclass
class SessionOutcome:
    state: CatState
    result: CatResult
    families: list[str]


def run_session(engine: IrtCatEngine, pool: list[FamilyMeta], true_params: dict[str, TrueParams], spec: str,
                claimed: str, theta: float, session_id: str, mode: str = "full", kind: str = "initial",
                seen: frozenset[str] = frozenset(), answer_override=None, theta_shift=None) -> SessionOutcome:
    """One CAT session. `answer_override(meta, p, honest) -> bool | None` lets the leak attack
    replace the honest Bernoulli answer for some items (None keeps the honest draw).
    `theta_shift(meta) -> float` adds a person-and-family specific term to θ (the synthetic world
    uses it for skill exposure, zero-mean given θ); without it the model is unidimensional."""
    rng = random.Random(f"responses|{session_id}")
    state = engine.start(spec, claimed, mode, kind, pool, set(seen))
    served = []
    while (meta := engine.next_family(state, pool, make_rng(SECRET, session_id, "select",
                                                              len(state.administered) + 1))) is not None:
        p = p_correct(theta + (theta_shift(meta) if theta_shift else 0.0), true_params[meta.id])
        honest = rng.random() < p
        forced = answer_override(meta, p, honest) if answer_override else None
        engine.record(state, meta.id, honest if forced is None else forced)
        served.append(meta.id)
    return SessionOutcome(state=state, result=engine.result(state), families=served)
