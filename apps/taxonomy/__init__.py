"""Taxonomy app package.

Exposes skill loading, normalization, and extraction.
"""
from .loader import SkillEntry, clean_key, get_skills_index, load_skills
from .normalize import SkillMatch, extract_skills, normalize_many, normalize_skill

__all__ = [
    "SkillEntry",
    "SkillMatch",
    "clean_key",
    "get_skills_index",
    "load_skills",
    "normalize_skill",
    "normalize_many",
    "extract_skills",
]
