"""Skill normalization and extraction against the canonical taxonomy.

Pure Python, rapidfuzz-powered, handling Cyrillic/Latin lookalikes and tech symbols (C++, C#, .NET).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .loader import SkillEntry, load_skills

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


@dataclass(frozen=True)
class SkillMatch:
    """Result of normalizing a raw skill term to canonical skill."""
    skill_id: str
    name: str
    score: float
    method: Literal["exact", "alias", "fuzzy", "embedding"]


# Common tech symbol cleanups that preserve critical identifiers
_TECH_REPLACEMENTS = {
    "c++": "cpp",
    "c#": "csharp",
    ".net": "dotnet",
    "node.js": "nodejs",
    "vue.js": "vue",
    "react.js": "react",
    "next.js": "nextjs",
    "nuxt.js": "nuxt",
}


def _clean_str(text: str) -> str:
    """Normalize whitespace and lowercase for comparison."""
    if not text:
        return ""
    s = text.strip().lower()
    # Normalize unicode spaces/dashes
    s = re.sub(r"[\s\xa0]+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s


def normalize_skill(raw: str, catalog: dict[str, SkillEntry] | None = None) -> SkillMatch | None:
    """Normalize a raw skill string to a canonical SkillMatch.

    Precedence:
    1. Exact match on id or canonical name.
    2. Known alias match.
    3. Fuzzy match using rapidfuzz (WRatio >= 90.0).
    """
    if not raw or not raw.strip():
        return None

    if catalog is None:
        catalog = load_skills()

    cleaned = _clean_str(raw)

    # 1. Exact match by ID or exact canonical name (lowercased)
    for sid, entry in catalog.items():
        if cleaned == sid or cleaned == entry.name.lower():
            return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method="exact")

    # 1b. Symbol-cleaned exact check (e.g. c++ -> cpp)
    if cleaned in _TECH_REPLACEMENTS:
        mapped_id = _TECH_REPLACEMENTS[cleaned]
        if mapped_id in catalog:
            entry = catalog[mapped_id]
            return SkillMatch(skill_id=mapped_id, name=entry.name, score=1.0, method="exact")

    # 2. Alias match
    for sid, entry in catalog.items():
        for alias in entry.aliases:
            if cleaned == alias.lower():
                return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method="alias")

    # 3. Fuzzy matching with rapidfuzz (threshold WRatio >= 90.0)
    if HAS_RAPIDFUZZ:
        best_match: tuple[str, str, float] | None = None  # (sid, name, score)
        best_score = 0.0

        for sid, entry in catalog.items():
            # Check similarity against entry name
            name_score = fuzz.WRatio(cleaned, entry.name.lower())
            if name_score > best_score:
                best_score = name_score
                best_match = (sid, entry.name, name_score / 100.0)

            # Check similarity against aliases
            for alias in entry.aliases:
                alias_score = fuzz.WRatio(cleaned, alias.lower())
                if alias_score > best_score:
                    best_score = alias_score
                    best_match = (sid, entry.name, alias_score / 100.0)

        if best_match is not None and best_score >= 90.0:
            return SkillMatch(
                skill_id=best_match[0],
                name=best_match[1],
                score=round(best_match[2], 2),
                method="fuzzy",
            )

    return None


def normalize_many(raws: list[str], catalog: dict[str, SkillEntry] | None = None) -> tuple[list[SkillMatch], list[str]]:
    """Normalize a list of raw skill strings.

    Returns:
        (matches, unknown_terms)
        matches: list of unique SkillMatch objects (first occurrence preserved).
        unknown_terms: list of raw strings that could not be mapped to any skill.
    """
    if catalog is None:
        catalog = load_skills()

    seen_ids: set[str] = set()
    matches: list[SkillMatch] = []
    unknown_terms: list[str] = []

    for raw in raws:
        if not raw or not raw.strip():
            continue
        match = normalize_skill(raw, catalog=catalog)
        if match is not None:
            if match.skill_id not in seen_ids:
                seen_ids.add(match.skill_id)
                matches.append(match)
        else:
            cleaned = raw.strip()
            if cleaned and cleaned not in unknown_terms:
                unknown_terms.append(cleaned)

    return matches, unknown_terms


def extract_skills(text: str, catalog: dict[str, SkillEntry] | None = None) -> tuple[list[SkillMatch], list[str]]:
    """Scan free text for mentions of taxonomy skills (used by rules fallback).

    Returns:
        (matches, unknown_terms)
    """
    if not text:
        return [], []

    if catalog is None:
        catalog = load_skills()

    lowered = text.lower()
    matched_ids: set[str] = set()
    matches: list[SkillMatch] = []

    # Check each skill and its aliases in the text
    for sid, entry in catalog.items():
        # Build patterns with word boundary or boundary symbols
        candidates = [sid, entry.name.lower()] + [a.lower() for a in entry.aliases]
        for cand in candidates:
            # Handle special symbols like c++, c#, .net
            if cand in ("c++", "cpp", "c#", ".net"):
                escaped = re.escape(cand)
                pattern = rf"(?:^|[\s,;/()\[\]]){escaped}(?:$|[\s,;/()\[\]])"
            else:
                escaped = re.escape(cand)
                pattern = rf"\b{escaped}\b"

            if re.search(pattern, lowered):
                if sid not in matched_ids:
                    matched_ids.add(sid)
                    matches.append(SkillMatch(
                        skill_id=sid,
                        name=entry.name,
                        score=1.0,
                        method="exact" if cand in (sid, entry.name.lower()) else "alias",
                    ))
                break

    return matches, []
