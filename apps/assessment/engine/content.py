"""Loader for the ML content files (content/grades.yaml, specializations.yaml, blueprints.yaml).

Pure (yaml only). Files are validated on load; a malformed file raises ContentError instead
of producing a half-configured engine. Results are cached per path.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..families.base import GRADES, SPECS

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"


class ContentError(ValueError):
    """A content file is missing or inconsistent."""


@dataclass(frozen=True)
class GradeDef:
    id: str
    name_ru: str
    theta_cut: float
    rating_cut: int
    start_theta: float
    descriptor_ru: str


@dataclass(frozen=True)
class TopicDef:
    id: str
    name_ru: str
    specs: tuple[str, ...]
    skills: tuple[str, ...]


@dataclass(frozen=True)
class Content:
    grades: tuple[GradeDef, ...]                      # ordered intern -> senior
    rating_base: float
    rating_per_theta: float
    specializations: dict[str, str]                   # id -> name_ru
    topics: dict[str, TopicDef]
    blueprints: dict[str, dict[str, float]]           # spec -> topic -> weight
    promotion_min_b_offset: float = -0.5              # promotion tests: items with b >= next cut + this

    def grade(self, gid: str) -> GradeDef:
        return self.grades[GRADES.index(gid)]

    @property
    def band_cuts(self) -> tuple[float, float, float]:
        """The three cuts separating intern|junior|middle|senior."""
        return tuple(g.theta_cut for g in self.grades[1:])  # type: ignore[return-value]

    def topics_for(self, spec: str) -> list[str]:
        return sorted(t for t, d in self.topics.items() if spec in d.specs)


def _read(path: Path):
    if not path.exists():
        raise ContentError(f"missing content file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@functools.lru_cache(maxsize=4)
def load_content(content_dir: str | None = None) -> Content:
    root = Path(content_dir) if content_dir else CONTENT_DIR
    g = _read(root / "grades.yaml")
    s = _read(root / "specializations.yaml")
    b = _read(root / "blueprints.yaml")

    grades = tuple(GradeDef(id=str(x["id"]), name_ru=str(x["name_ru"]), theta_cut=float(x["theta_cut"]),
                            rating_cut=int(x["rating_cut"]), start_theta=float(x["start_theta"]),
                            descriptor_ru=str(x["descriptor_ru"]).strip()) for x in g.get("grades", []))
    if tuple(x.id for x in grades) != GRADES:
        raise ContentError(f"grades.yaml must list {GRADES} in order")
    cuts = [x.theta_cut for x in grades]
    if cuts != sorted(cuts) or len(set(cuts)) != len(cuts):
        raise ContentError(f"theta cuts must increase: {cuts}")
    scale = g.get("scale", {})
    base, per = float(scale.get("rating_base", 1000)), float(scale.get("rating_per_theta", 200))
    for x in grades:
        if x.rating_cut != round(base + per * x.theta_cut):
            raise ContentError(f"{x.id}: rating_cut {x.rating_cut} != {base} + {per}·{x.theta_cut}")

    specs = {str(x["id"]): str(x["name_ru"]) for x in s.get("specializations", [])}
    if tuple(sorted(specs)) != tuple(sorted(SPECS)):
        raise ContentError(f"specializations.yaml must define {SPECS}")
    topics: dict[str, TopicDef] = {}
    for x in s.get("topics", []):
        t = TopicDef(id=str(x["id"]), name_ru=str(x["name_ru"]), specs=tuple(x["specs"]),
                     skills=tuple(str(k) for k in x.get("skills", [])))
        if t.id in topics:
            raise ContentError(f"duplicate topic {t.id}")
        if not t.specs or any(sp not in SPECS for sp in t.specs):
            raise ContentError(f"topic {t.id}: bad specs {t.specs}")
        topics[t.id] = t

    blueprints: dict[str, dict[str, float]] = {}
    for spec, weights in (b.get("blueprints") or {}).items():
        if spec not in SPECS:
            raise ContentError(f"blueprint for unknown spec {spec}")
        weights = {str(k): float(v) for k, v in weights.items()}
        for topic, w in weights.items():
            if topic not in topics or spec not in topics[topic].specs:
                raise ContentError(f"blueprint {spec}: topic {topic} is not a {spec} topic")
            if w <= 0:
                raise ContentError(f"blueprint {spec}: weight of {topic} must be > 0")
        if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
            raise ContentError(f"blueprint {spec}: weights sum to {sum(weights.values())}, not 1")
        missing = sorted(t for t, d in topics.items() if spec in d.specs and t not in weights)
        if missing:
            raise ContentError(f"blueprint {spec}: topics without a weight: {missing}")
        blueprints[spec] = dict(sorted(weights.items()))
    if sorted(blueprints) != sorted(SPECS):
        raise ContentError(f"blueprints.yaml must cover {SPECS}")

    promo = b.get("promotion") or {}
    offset = float(promo.get("min_b_offset", -0.5))
    if not math.isfinite(offset) or not -2.0 <= offset <= 0.0:
        raise ContentError(f"promotion.min_b_offset must be in [-2, 0], got {offset}")

    return Content(grades=grades, rating_base=base, rating_per_theta=per, specializations=specs,
                   topics=topics, blueprints=blueprints, promotion_min_b_offset=offset)
