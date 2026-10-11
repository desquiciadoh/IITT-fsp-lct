"""Test Twins: a screening blueprint and two parallel forms (ML-12, AI-14; ARCHITECTURE §2.12).

A position's skills become a blueprint (`blueprint_for`), the blueprint becomes n topic slots, and
each slot gets one family. Both twins use the SAME family in each slot, generated from different
seeds: isomorphic instances with identical a, b, c and time limit, so the two forms have the same
topic profile and the same test information function by construction, while no instance (and so
no answer) is shared. Within a topic the slots rotate over its families, best information at the
target grade's θ first, so one family does not fill a whole topic.

The instances are generated with the caller's secret (`make_rng`); a constant secret in the code
would let anyone regenerate them and their keys. Keys and fingerprints never leave this module:
`to_dict()` returns the candidate views only.

Pure: no Django, no ORM, no core.enums.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..families.base import GRADES, SPECS, FamilyMeta, Grade, Spec
from ..families.registry import active_metas, all_families, make_rng
from .blueprint import blueprint_for
from .content import Content, load_content
from .irt import information
from .policy import band_of

TIF_GRID = np.linspace(-3.0, 3.0, 25)
MAX_FINGERPRINT_RETRIES = 20


@dataclass(frozen=True)
class TwinItem:
    seq: int
    topic: str
    topic_ru: str
    level: Grade
    family_id: str
    format: str
    a: float
    b: float
    c: float
    time_limit_s: int
    fingerprint: str                    # server-side only, never in to_dict()
    view: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "topic": self.topic, "topic_ru": self.topic_ru, "level": self.level,
                "family_id": self.family_id, "format": self.format, "a": self.a, "b": self.b, "c": self.c,
                "time_limit_s": self.time_limit_s, "view": self.view}


@dataclass(frozen=True)
class TwinTest:
    name: str
    items: list[TwinItem]

    @property
    def mean_difficulty(self) -> float:
        return float(np.mean([it.b for it in self.items]))

    @property
    def mean_discrimination(self) -> float:
        return float(np.mean([it.a for it in self.items]))

    @property
    def total_duration_s(self) -> int:
        return sum(it.time_limit_s for it in self.items)

    def tif(self) -> np.ndarray:
        return sum((information(TIF_GRID, it.a, it.b, it.c) for it in self.items), np.zeros_like(TIF_GRID))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "total_items": len(self.items),
                "mean_difficulty": round(self.mean_difficulty, 3),
                "mean_discrimination": round(self.mean_discrimination, 3),
                "total_duration_s": self.total_duration_s,
                "items": [it.to_dict() for it in self.items]}


@dataclass(frozen=True)
class TwinsComparison:
    difficulty_diff: float
    discrimination_diff: float
    duration_diff: int
    tif_max_abs_diff: float
    identical_fingerprints: int
    topic_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {"difficulty_diff": round(self.difficulty_diff, 3),
                "discrimination_diff": round(self.discrimination_diff, 3),
                "duration_diff": self.duration_diff, "tif_max_abs_diff": round(self.tif_max_abs_diff, 4),
                "identical_fingerprints": self.identical_fingerprints, "topic_match": self.topic_match}


@dataclass(frozen=True)
class TestTwinsResult:
    __test__ = False                    # not a pytest class
    spec: Spec
    target_grade: Grade
    blueprint: list[dict[str, Any]]
    twin_a: TwinTest
    twin_b: TwinTest
    comparison: TwinsComparison

    def to_dict(self) -> dict[str, Any]:
        return {"specialization": self.spec, "target_grade": self.target_grade, "blueprint": self.blueprint,
                "twin_a": self.twin_a.to_dict(), "twin_b": self.twin_b.to_dict(),
                "comparison": self.comparison.to_dict()}


def allocate_slots(blueprint: Sequence[tuple[str, float]], n_items: int) -> list[str]:
    """n_items topic slots by largest remainder (Hamilton): floor(w·n) each, the rest to the largest
    fractional parts, ties by topic id. Slots are listed in blueprint order."""
    if n_items <= 0 or not blueprint:
        return []
    raw = {t: w * n_items for t, w in blueprint}
    count = {t: int(np.floor(r)) for t, r in raw.items()}
    rest = n_items - sum(count.values())
    for t in sorted(raw, key=lambda t: (-(raw[t] - count[t]), t))[:rest]:
        count[t] += 1
    return [t for t, _ in blueprint for _ in range(count[t])]


def create_test_twins(spec: Spec, skills: Sequence[str], secret: bytes | str, target_grade: Grade = "middle",
                      n_items: int = 8, seed: int | str = 0, content: Content | None = None) -> TestTwinsResult:
    """Two parallel forms for a screening test of `n_items` slots. `secret` is the server's item
    secret (never a constant); `seed` distinguishes requests (e.g. the position id)."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    if target_grade not in GRADES:
        raise ValueError(f"unknown grade: {target_grade!r}")
    if not 1 <= n_items <= 40:
        raise ValueError(f"n_items must be in 1..40, got {n_items}")
    content = content or load_content()
    registry = all_families()
    by_topic: dict[str, list[FamilyMeta]] = {}
    for m in active_metas(spec):
        by_topic.setdefault(m.topic, []).append(m)

    blueprint = blueprint_for(spec, list(skills), content=content)
    slots = allocate_slots(blueprint, n_items)
    theta = next(g.start_theta for g in content.grades if g.id == target_grade)
    used: dict[str, int] = {}
    items_a: list[TwinItem] = []
    items_b: list[TwinItem] = []
    for seq, topic in enumerate(slots, start=1):
        fams = by_topic.get(topic)
        if not fams:
            raise ValueError(f"no active family for topic {topic!r} in {spec}")
        ranked = sorted(fams, key=lambda m: (-float(information(theta, m.a, m.b, m.c)), m.id))
        meta = ranked[used.get(topic, 0) % len(ranked)]
        used[topic] = used.get(topic, 0) + 1
        fam = registry[meta.id]
        inst_a = fam.generate(make_rng(secret, f"twins|{seed}|{spec}|A", meta.id, seq))
        for retry in range(MAX_FINGERPRINT_RETRIES):
            inst_b = fam.generate(make_rng(secret, f"twins|{seed}|{spec}|B", meta.id, seq * 100 + retry))
            if inst_b.fingerprint != inst_a.fingerprint:
                break
        topic_ru = content.topics[topic].name_ru
        for items, inst in ((items_a, inst_a), (items_b, inst_b)):
            items.append(TwinItem(seq=seq, topic=topic, topic_ru=topic_ru, level=band_of(meta.b, content),
                                  family_id=meta.id, format=meta.format, a=meta.a, b=meta.b, c=meta.c,
                                  time_limit_s=meta.time_limit_s, fingerprint=inst.fingerprint, view=inst.view()))

    twin_a = TwinTest("Вариант А", items_a)
    twin_b = TwinTest("Вариант Б", items_b)
    comparison = TwinsComparison(
        difficulty_diff=abs(twin_a.mean_difficulty - twin_b.mean_difficulty),
        discrimination_diff=abs(twin_a.mean_discrimination - twin_b.mean_discrimination),
        duration_diff=abs(twin_a.total_duration_s - twin_b.total_duration_s),
        tif_max_abs_diff=float(np.max(np.abs(twin_a.tif() - twin_b.tif()))),
        identical_fingerprints=len({i.fingerprint for i in items_a} & {i.fingerprint for i in items_b}),
        topic_match=[registry[i.family_id].meta.topic for i in items_a]
        == [registry[i.family_id].meta.topic for i in items_b] == slots,
    )
    bp = [{"topic": t, "name_ru": content.topics[t].name_ru, "weight": w, "items_allocated": slots.count(t)}
          for t, w in blueprint]
    return TestTwinsResult(spec=spec, target_grade=target_grade, blueprint=bp, twin_a=twin_a, twin_b=twin_b,
                           comparison=comparison)


def generate_twins_for_position(pos: dict[str, Any], secret: bytes | str, n_items: int = 8) -> TestTwinsResult:
    """Twins for a position dict (specialization, grades, must_skills, nice_skills, position_id)."""
    grades = list(pos.get("grades") or ["middle"])
    skills = list(dict.fromkeys([*pos.get("must_skills", ()), *pos.get("nice_skills", ())]))
    return create_test_twins(spec=pos.get("specialization", "backend"), skills=skills, secret=secret,
                             target_grade=grades[0], n_items=n_items, seed=pos.get("position_id", 0))
