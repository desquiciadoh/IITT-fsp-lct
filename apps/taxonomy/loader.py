"""Skill taxonomy loader.

Loads and caches the skill catalog from YAML.
Pure Python, free of Django ORM or views.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SkillEntry:
    """Represents a canonical skill entry from the taxonomy catalog."""
    id: str
    name: str
    topic: str
    aliases: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)


_SKILLS_CACHE: dict[str, SkillEntry] | None = None
_BY_KEY_CACHE: dict[str, str] | None = None
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "content" / "skills.yaml"


def clean_key(text: str) -> str:
    """Normalize text for exact/alias index lookup (NFKC, lowercase, trimmed, unified whitespace/dashes)."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).strip().lower()
    s = re.sub(r"[\s\xa0]+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s


def load_skills(path: str | Path | None = None, force_reload: bool = False) -> dict[str, SkillEntry]:
    """Load skill catalog from yaml file.

    Returns:
        dict mapping skill_id to SkillEntry.
    """
    global _SKILLS_CACHE, _BY_KEY_CACHE
    if _SKILLS_CACHE is not None and not force_reload:
        return _SKILLS_CACHE

    target_path = Path(path) if path else _DEFAULT_PATH

    if not target_path.exists():
        # Fallback to relative lookup if run from different working directory
        alt_path = Path.cwd() / "content" / "skills.yaml"
        if alt_path.exists():
            target_path = alt_path
        else:
            raise FileNotFoundError(f"Skills catalog not found at {target_path} or {alt_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []

    catalog: dict[str, SkillEntry] = {}
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue
        entry = SkillEntry(
            id=str(item["id"]).strip().lower(),
            name=str(item.get("name", item["id"])).strip(),
            topic=str(item.get("topic", "general")).strip(),
            aliases=[str(a).strip().lower() for a in item.get("aliases", []) if a],
            related=[str(r).strip().lower() for r in item.get("related", []) if r],
        )
        catalog[entry.id] = entry

    _SKILLS_CACHE = catalog
    # Invalidate by_key cache on reload
    _BY_KEY_CACHE = None
    return catalog


def get_skills_index(path: str | Path | None = None, force_reload: bool = False) -> dict[str, str]:
    """Prebuild and return the by_key index mapping cleaned id/name/aliases to canonical skill_id."""
    global _BY_KEY_CACHE
    if _BY_KEY_CACHE is not None and not force_reload:
        return _BY_KEY_CACHE

    catalog = load_skills(path=path, force_reload=force_reload)
    by_key: dict[str, str] = {}

    for sid, entry in catalog.items():
        by_key[sid] = sid
        ck_id = clean_key(sid)
        if ck_id:
            by_key[ck_id] = sid
        ck_name = clean_key(entry.name)
        if ck_name:
            by_key[ck_name] = sid
        for alias in entry.aliases:
            ck_alias = clean_key(alias)
            if ck_alias:
                by_key[ck_alias] = sid

    _BY_KEY_CACHE = by_key
    return by_key
