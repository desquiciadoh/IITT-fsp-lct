"""Skill taxonomy loader.

Loads and caches the skill catalog from YAML.
Pure Python, free of Django ORM or views.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "content" / "skills.yaml"


def load_skills(path: str | Path | None = None, force_reload: bool = False) -> dict[str, SkillEntry]:
    """Load skill catalog from yaml file.

    Returns:
        dict mapping skill_id to SkillEntry.
    """
    global _SKILLS_CACHE
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
    return catalog
