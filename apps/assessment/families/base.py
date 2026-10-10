"""Item family contract (ML.md §3): metadata, rendered instances, the family protocol.

Pure: no Django, no ORM, no core.enums. All randomness comes from the `rng` passed to
`generate()`, so the same rng state renders the same instance in any process.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Spec = Literal["backend", "frontend", "ml_data"]
Grade = Literal["intern", "junior", "middle", "senior"]          # ordered
ItemFormat = Literal["code_output", "find_bug", "sql_result", "complexity",
                     "numeric_scenario", "concept_mcq"]
InputKind = Literal["choice", "number", "text"]

SPECS: tuple[str, ...] = ("backend", "frontend", "ml_data")
GRADES: tuple[str, ...] = ("intern", "junior", "middle", "senior")
ITEM_FORMATS: tuple[str, ...] = ("code_output", "find_bug", "sql_result", "complexity",
                                 "numeric_scenario", "concept_mcq")
INPUT_KINDS: tuple[str, ...] = ("choice", "number", "text")


@dataclass(frozen=True)
class FamilyMeta:
    id: str                    # "be.sql.group_having.v2"
    version: int
    specs: tuple[Spec, ...]    # shared families list every spec
    topic: str                 # must exist in content/specializations.yaml
    skills: tuple[str, ...]    # skill ids from content/skills.yaml (AI-owned)
    format: ItemFormat
    a: float                   # discrimination
    b: float                   # difficulty (expert prior, recalibrated later)
    c: float                   # 1/len(options) for choice, 0 for typed answers
    time_limit_s: int


@dataclass
class Instance:
    stem_md: str
    input: InputKind
    key: Any                                      # SERVER-SIDE ONLY -> AssessmentItem.key
    fingerprint: str                              # sha256 of the drawn PARAMETERS (not the seed)
    code: dict[str, str] | None = None            # {"lang": "python"|"javascript"|"sql", "text": ...}
    options: list[dict[str, str]] | None = None   # [{"id": opaque, "text_md": ...}], shuffled, distinct

    def view(self) -> dict:
        """What the candidate sees. Never the key or the fingerprint."""
        return {
            "stem_md": self.stem_md,
            "input": self.input,
            "code": {"lang": self.code["lang"], "text": self.code["text"]} if self.code else None,
            "options": [{"id": o["id"], "text_md": o["text_md"]} for o in self.options]
            if self.options else None,
        }


class ItemFamily(Protocol):
    meta: FamilyMeta

    def generate(self, rng: random.Random) -> Instance: ...

    def is_correct(self, key: Any, answer: dict) -> bool: ...   # {"option_id": str} | {"value": str}

    def oracle(self, inst: Instance) -> Any: ...                # independent recomputation; verify only


def fingerprint_of(params: Any) -> str:
    """sha256 of the canonical JSON of the drawn parameters."""
    blob = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def option_id(rng: random.Random) -> str:
    """An opaque option id drawn from rng; never positional, never derived from the answer."""
    return f"o{rng.getrandbits(32):08x}"
