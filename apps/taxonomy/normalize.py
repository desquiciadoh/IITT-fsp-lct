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


_WORD_CHARS = "A-Za-zА-Яа-яЁё0-9_"


def _key_pattern(key: str) -> re.Pattern[str]:
    """Free-text pattern for one lower-cased taxonomy key."""
    if len(key) <= 2:
        # Short keys ("go", "c", "ml", "tf", "c#") are matched case-sensitively in their usual
        # spellings only (Go/GO, C, ML, TF, C#), so "ready to go", "C++", "C-level" and
        # "TF-IDF" do not produce skills.
        variants = sorted({key.upper(), key[:1].upper() + key[1:]})
        body = "|".join(re.escape(v) for v in variants)
        return re.compile(rf"(?<![{_WORD_CHARS}.+#])(?:{body})(?![{_WORD_CHARS}+#]|-[A-Za-z])")
    escaped = re.escape(key)
    if not key[-1].isalnum():
        # "c++", "c#": a version may follow ("C++17"), another symbol may not
        return re.compile(rf"(?<![{_WORD_CHARS}]){escaped}(?![A-Za-zА-Яа-яЁё_+#])", re.IGNORECASE)
    return re.compile(rf"(?<![{_WORD_CHARS}]){escaped}(?![{_WORD_CHARS}])", re.IGNORECASE)


# (key, needles, pattern): the regex runs only if a needle occurs in the text (a fast substring
# check); long keys are looked up in the lower-cased text, short keys in their exact spellings.
_KeyPatterns = list[tuple[str, tuple[str, ...], re.Pattern[str]]]
_PATTERNS_CACHE: tuple[dict[str, SkillEntry], list[tuple[str, SkillEntry, _KeyPatterns]]] | None = None


def _catalog_patterns(catalog: dict[str, SkillEntry]) -> list[tuple[str, SkillEntry, _KeyPatterns]]:
    """Compile the free-text patterns once per catalog object."""
    global _PATTERNS_CACHE
    if _PATTERNS_CACHE is not None and _PATTERNS_CACHE[0] is catalog:
        return _PATTERNS_CACHE[1]
    compiled = []
    for sid, entry in catalog.items():
        keys = list(dict.fromkeys(k for k in [sid, clean_key(entry.name), *entry.aliases] if k))
        patterns = []
        for key in keys:
            needles = tuple({key.upper(), key[:1].upper() + key[1:]}) if len(key) <= 2 else (key,)
            patterns.append((key, needles, _key_pattern(key)))
        compiled.append((sid, entry, patterns))
    _PATTERNS_CACHE = (catalog, compiled)
    return compiled


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
    matches: list[SkillMatch] = []
    for sid, entry, patterns in _catalog_patterns(catalog):
        for key, needles, pattern in patterns:
            haystack = text if len(key) <= 2 else lowered
            if any(needle in haystack for needle in needles) and pattern.search(text):
                matches.append(SkillMatch(
                    skill_id=sid,
                    name=entry.name,
                    score=1.0,
                    method="exact" if key in (sid, clean_key(entry.name)) else "alias",
                ))
                break

    return matches, []
