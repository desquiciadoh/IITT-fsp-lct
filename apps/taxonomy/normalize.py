"""Skill normalization and extraction against the canonical taxonomy.

Pure Python, rapidfuzz-powered (OSA Damerau distance), handling Cyrillic/Latin lookalikes,
tech symbols (C++, C#, .NET), version suffixes, and O(1) indexed lookups.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from rapidfuzz.distance import OSA

from .loader import SkillEntry, clean_key, get_skills_index, load_skills


@dataclass(frozen=True)
class SkillMatch:
    """Result of normalizing a raw skill term to canonical skill."""
    skill_id: str
    name: str
    score: float
    method: Literal["exact", "alias", "fuzzy", "embedding"]


# Lookalike mapping: Cyrillic to Latin for mixed-script tokens
_CYRILLIC_LOOKALIKES = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "к": "k", "м": "m", "т": "t",
    "н": "h", "в": "b",
}

# Canonical spellings for tech identifiers with special punctuation or names
_CANONICAL_SPELLINGS = {
    "c++": "cpp",
    "си++": "cpp",
    "с++": "cpp",
    "плюсы": "cpp",
    "cpp": "cpp",
    "c/c++": "cpp",
    "c#": "csharp",
    "c-sharp": "csharp",
    "c sharp": "csharp",
    "си шарп": "csharp",
    "си-шарп": "csharp",
    "с#": "csharp",
    ".net": "dotnet",
    "dot net": "dotnet",
    "dotnet": "dotnet",
    ".net core": "dotnet",
    "asp.net": "dotnet",
    "asp.net core": "dotnet",
    "дотнет": "dotnet",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "node js": "nodejs",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue js": "vue",
    "next.js": "nextjs",
    "nextjs": "nextjs",
    "next js": "nextjs",
    "nuxt.js": "nuxt",
    "nuxtjs": "nuxt",
    "nuxt js": "nuxt",
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    "js": "javascript",
    "жс": "javascript",
    "go": "golang",
    "го": "golang",
    "голанг": "golang",
    "постгря": "postgresql",
    "drf": "drf",
}


def _prenormalize_token(raw: str) -> str:
    """Apply NFKC, lowercase, whitespace collapse, dashes and lookalike mapping."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw).strip().lower()
    s = re.sub(r"[\s\xa0]+", " ", s)
    s = s.replace("–", "-").replace("—", "-")

    # If already in canonical spellings, preserve as is
    if s in _CANONICAL_SPELLINGS:
        return s

    # Map Cyrillic lookalikes only if token is mostly Latin
    latin_count = sum(1 for c in s if "a" <= c <= "z")
    cyrillic_count = sum(1 for c in s if "\u0400" <= c <= "\u04ff")
    if latin_count > 0 and latin_count >= cyrillic_count:
        chars = [_CYRILLIC_LOOKALIKES.get(c, c) for c in s]
        s = "".join(chars)

    return s


def _strip_version_suffix(token: str) -> str:
    """Strip version numbers e.g. 'python 3.12' -> 'python', 'vue3' -> 'vue'."""
    # Pattern: space followed by version like '3.12', 'v2', '14'
    s = re.sub(r"\s+(?:v|version\s*)?\d+(?:\.\d+)*$", "", token).strip()
    return s


def normalize_skill(raw: str, catalog: dict[str, SkillEntry] | None = None) -> SkillMatch | None:
    """Normalize a raw skill string to a canonical SkillMatch.

    Precedence:
    1. Exact match on id or canonical name.
    2. Known alias match (O(1) via by_key index).
    3. Canonical tech spellings / lookalikes / version stripping.
    4. Guarded fuzzy match using rapidfuzz OSA distance (threshold len >= 4, first letter match).
    """
    if not raw or not raw.strip():
        return None

    if catalog is None:
        catalog = load_skills()

    by_key = get_skills_index()

    prenorm = _prenormalize_token(raw)
    if not prenorm:
        return None

    # 1. Exact/Alias lookup in by_key index
    if prenorm in by_key:
        sid = by_key[prenorm]
        entry = catalog[sid]
        method: Literal["exact", "alias"] = "exact" if prenorm in (sid, clean_key(entry.name)) else "alias"
        return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method=method)

    # 2. Canonical tech spellings
    if prenorm in _CANONICAL_SPELLINGS:
        sid = _CANONICAL_SPELLINGS[prenorm]
        if sid in catalog:
            entry = catalog[sid]
            return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method="alias")

    # 3. Version suffix stripping (e.g. 'python 3.12' -> 'python', 'vue3' -> 'vue')
    stripped = _strip_version_suffix(prenorm)
    if stripped != prenorm and stripped in by_key:
        sid = by_key[stripped]
        entry = catalog[sid]
        return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method="alias")

    # Check attached digits e.g. vue3 -> vue
    m_attached = re.match(r"^([a-zа-яё]+)\s*(\d+)$", prenorm)
    if m_attached:
        prefix = m_attached.group(1)
        if prefix in by_key:
            sid = by_key[prefix]
            entry = catalog[sid]
            return SkillMatch(skill_id=sid, name=entry.name, score=1.0, method="alias")

    # 4. Guarded fuzzy matching via rapidfuzz OSA (Damerau) distance
    # Requirements:
    # - input len >= 4
    # - candidate len >= 4
    # - first letter must match
    # - length ratio in [0.75, 1.33]
    # - OSA distance <= 1 for len 4..9, <= 2 for len >= 10
    # - ambiguous best distance -> no match
    if len(prenorm) >= 4:
        input_len = len(prenorm)
        max_dist = 1 if input_len < 10 else 2
        first_char = prenorm[0]

        candidates: list[tuple[int, str, str]] = []  # (distance, sid, cand_key)

        for cand_key, sid in by_key.items():
            cand_len = len(cand_key)
            if cand_len < 4:
                continue
            if cand_key[0] != first_char:
                continue
            ratio = input_len / cand_len
            if not (0.75 <= ratio <= 1.33):
                continue

            dist = OSA.distance(prenorm, cand_key)
            if dist <= max_dist:
                candidates.append((dist, sid, cand_key))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            best_dist = candidates[0][0]
            # Check for ambiguity among candidates with best_dist
            best_sids = {sid for dist, sid, _ in candidates if dist == best_dist}
            if len(best_sids) == 1:
                best_sid = next(iter(best_sids))
                best_key = candidates[0][2]
                max_len = max(input_len, len(best_key))
                score = 1.0 - (best_dist / max_len)
                entry = catalog[best_sid]
                return SkillMatch(
                    skill_id=best_sid,
                    name=entry.name,
                    score=round(score, 2),
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
    """Scan free text for mentions of taxonomy skills (used by rules fallback and phrase grounding).

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
        candidates = [sid, entry.name.lower()] + [a.lower() for a in entry.aliases]
        for cand in candidates:
            # Handle special symbols like c++, c#, .net
            if cand in ("c++", "cpp", "c#", ".net", "drf"):
                escaped = re.escape(cand)
                pattern = rf"(?:^|[\s,;/()\[\]]){escaped}(?:$|[\s,;/()\[\]])"
            else:
                escaped = re.escape(cand)
                pattern = rf"(?<![A-Za-zА-Яа-я0-9_]){escaped}(?![A-Za-zА-Яа-я0-9_])"

            if re.search(pattern, lowered):
                if sid not in matched_ids:
                    matched_ids.add(sid)
                    matches.append(SkillMatch(
                        skill_id=sid,
                        name=entry.name,
                        score=1.0,
                        method="exact" if cand in (sid, clean_key(entry.name)) else "alias",
                    ))
                break

    return matches, []
