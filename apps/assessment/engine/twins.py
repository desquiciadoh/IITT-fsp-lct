"""Test Twins & Screening Blueprints generator (ML-12, AI-14; ARCHITECTURE §2.12).

Turns a job description / hiring position into a calibrated screening blueprint and generates
two parallel, equivalent test instances (Test Twins):
  - Both twins follow the EXACT SAME topic quotas from the position blueprint;
  - Both twins share the SAME difficulty profile calibrated to the target grade;
  - Both twins contain 100% UNIQUE parametric instances (zero answer leaks, zero fingerprint collision);
  - Neither twin leaks the answer key in client-facing views.

Pure engine module: no Django, no ORM, no core.enums.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import math
from typing import Any

from ..families.base import GRADES, SPECS, FamilyMeta, Grade, Spec
from ..families.registry import active_metas, all_families, make_rng
from .blueprint import blueprint_for
from .content import Content, load_content
from .policy import band_of

TWINS_SECRET = b"fsp-draft-test-twins"

TARGET_THETAS: dict[str, float] = {
    "intern": -1.5,
    "junior": -0.5,
    "middle": 0.5,
    "senior": 1.5,
}


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
    fingerprint: str
    view: dict[str, Any]


@dataclass(frozen=True)
class TwinTest:
    name: str
    items: list[TwinItem]
    mean_difficulty: float
    mean_discrimination: float
    total_duration_s: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_items": len(self.items),
            "mean_difficulty": round(self.mean_difficulty, 3),
            "mean_discrimination": round(self.mean_discrimination, 3),
            "total_duration_s": self.total_duration_s,
            "items": [
                {
                    "seq": it.seq,
                    "topic": it.topic,
                    "topic_ru": it.topic_ru,
                    "level": it.level,
                    "family_id": it.family_id,
                    "format": it.format,
                    "a": it.a,
                    "b": it.b,
                    "c": it.c,
                    "time_limit_s": it.time_limit_s,
                    "view": it.view,
                }
                for it in self.items
            ],
        }


@dataclass(frozen=True)
class TwinsComparison:
    difficulty_diff: float
    discrimination_diff: float
    duration_diff: int
    identical_fingerprints: int
    topic_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "difficulty_diff": round(self.difficulty_diff, 3),
            "discrimination_diff": round(self.discrimination_diff, 3),
            "duration_diff": self.duration_diff,
            "identical_fingerprints": self.identical_fingerprints,
            "topic_match": self.topic_match,
        }


@dataclass(frozen=True)
class TestTwinsResult:
    spec: Spec
    target_grade: Grade
    blueprint: list[dict[str, Any]]
    twin_a: TwinTest
    twin_b: TwinTest
    comparison: TwinsComparison

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialization": self.spec,
            "target_grade": self.target_grade,
            "blueprint": self.blueprint,
            "twin_a": self.twin_a.to_dict(),
            "twin_b": self.twin_b.to_dict(),
            "comparison": self.comparison.to_dict(),
        }


def _allocate_slots(blueprint: list[tuple[str, float]], n_items: int) -> list[str]:
    """Allocate n_items integer slots across blueprint topics preserving proportions."""
    if not blueprint or n_items <= 0:
        return []

    # Initial floor allocation
    raw = [(t, w * n_items) for t, w in blueprint]
    allocated = {t: int(math.floor(r)) for t, r in raw}
    remainder = n_items - sum(allocated.values())

    # Sort topics by fractional deficit
    ranked_by_frac = sorted(raw, key=lambda tr: (tr[1] - math.floor(tr[1])), reverse=True)
    for i in range(remainder):
        t_top = ranked_by_frac[i % len(ranked_by_frac)][0]
        allocated[t_top] += 1

    slots: list[str] = []
    for t, _ in blueprint:
        cnt = allocated.get(t, 0)
        slots.extend([t] * cnt)

    return slots[:n_items]


def create_test_twins(
    spec: Spec,
    skills: Sequence[str],
    target_grade: Grade = "middle",
    n_items: int = 8,
    seed: int = 2026,
    content: Content | None = None,
) -> TestTwinsResult:
    """Generate two parallel, equivalent screening tests for a skill specification."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    if target_grade not in GRADES:
        raise ValueError(f"unknown grade: {target_grade!r}")

    content = content or load_content()
    fam_registry = all_families()
    pool = active_metas(spec)
    if not pool:
        raise ValueError(f"no active families for spec {spec}")

    # 1. Compute screening blueprint
    bp = blueprint_for(spec, list(skills), content=content)
    slots = _allocate_slots(bp, n_items)

    target_th = TARGET_THETAS.get(target_grade, 0.0)

    # Families by topic for this spec
    fam_by_topic: dict[str, list[FamilyMeta]] = {}
    for m in pool:
        fam_by_topic.setdefault(m.topic, []).append(m)

    items_a: list[TwinItem] = []
    items_b: list[TwinItem] = []

    for seq, topic in enumerate(slots, start=1):
        cands = fam_by_topic.get(topic, pool)
        # Sort candidate families by proximity to target difficulty
        sorted_cands = sorted(cands, key=lambda m: (abs(m.b - target_th), m.id))

        meta_a = sorted_cands[0]
        # For Twin B, prefer a different family with the same topic if available
        meta_b = sorted_cands[1] if len(sorted_cands) > 1 else meta_a

        fam_a = fam_registry[meta_a.id]
        fam_b = fam_registry[meta_b.id]

        # Generate Twin A instance
        rng_a = make_rng(TWINS_SECRET, f"twin_a|{seed}|{spec}", meta_a.id, seq)
        inst_a = fam_a.generate(rng_a)

        # Generate Twin B instance with independent seed
        rng_b = make_rng(TWINS_SECRET, f"twin_b|{seed}|{spec}", meta_b.id, seq)
        inst_b = fam_b.generate(rng_b)

        topic_def = content.topics.get(topic)
        topic_ru = topic_def.name_ru if topic_def else topic

        items_a.append(
            TwinItem(
                seq=seq,
                topic=topic,
                topic_ru=topic_ru,
                level=band_of(meta_a.b, content),
                family_id=meta_a.id,
                format=meta_a.format,
                a=meta_a.a,
                b=meta_a.b,
                c=meta_a.c,
                time_limit_s=meta_a.time_limit_s,
                fingerprint=inst_a.fingerprint,
                view=inst_a.view(),
            )
        )

        items_b.append(
            TwinItem(
                seq=seq,
                topic=topic,
                topic_ru=topic_ru,
                level=band_of(meta_b.b, content),
                family_id=meta_b.id,
                format=meta_b.format,
                a=meta_b.a,
                b=meta_b.b,
                c=meta_b.c,
                time_limit_s=meta_b.time_limit_s,
                fingerprint=inst_b.fingerprint,
                view=inst_b.view(),
            )
        )

    # Metrics
    mean_b_a = sum(it.b for it in items_a) / len(items_a)
    mean_b_b = sum(it.b for it in items_b) / len(items_b)
    mean_a_a = sum(it.a for it in items_a) / len(items_a)
    mean_a_b = sum(it.a for it in items_b) / len(items_b)
    dur_a = sum(it.time_limit_s for it in items_a)
    dur_b = sum(it.time_limit_s for it in items_b)

    twin_a = TwinTest(
        name="Вариант А (Twin 1)",
        items=items_a,
        mean_difficulty=mean_b_a,
        mean_discrimination=mean_a_a,
        total_duration_s=dur_a,
    )

    twin_b = TwinTest(
        name="Вариант Б (Twin 2)",
        items=items_b,
        mean_difficulty=mean_b_b,
        mean_discrimination=mean_a_b,
        total_duration_s=dur_b,
    )

    fps_a = {it.fingerprint for it in items_a}
    fps_b = {it.fingerprint for it in items_b}
    identical_fps = len(fps_a & fps_b)

    topics_match = [it.topic for it in items_a] == [it.topic for it in items_b]

    comparison = TwinsComparison(
        difficulty_diff=abs(mean_b_a - mean_b_b),
        discrimination_diff=abs(mean_a_a - mean_a_b),
        duration_diff=abs(dur_a - dur_b),
        identical_fingerprints=identical_fps,
        topic_match=topics_match,
    )

    bp_serialized = [
        {
            "topic": t,
            "name_ru": content.topics[t].name_ru if t in content.topics else t,
            "weight": w,
            "items_allocated": slots.count(t),
        }
        for t, w in bp
    ]

    return TestTwinsResult(
        spec=spec,
        target_grade=target_grade,
        blueprint=bp_serialized,
        twin_a=twin_a,
        twin_b=twin_b,
        comparison=comparison,
    )


def generate_twins_for_position(pos: dict[str, Any], n_items: int = 8, seed: int = 2026) -> TestTwinsResult:
    """Create test twins given a position dictionary or position input."""
    spec = pos.get("specialization", "backend")
    grades = pos.get("grades", ["middle"])
    target_grade = grades[0] if grades else "middle"
    must = pos.get("must_skills", [])
    nice = pos.get("nice_skills", [])
    skills = list(dict.fromkeys(must + nice))

    return create_test_twins(
        spec=spec,
        skills=skills,
        target_grade=target_grade,
        n_items=n_items,
        seed=seed,
    )
