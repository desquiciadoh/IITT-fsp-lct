"""Taxonomy app package.

Exposes skill loading, normalization, and extraction.
"""
from .loader import SkillEntry, load_skills
from .normalize import SkillMatch, extract_skills, normalize_many, normalize_skill

__all__ = [
    "SkillEntry",
    "SkillMatch",
    "load_skills",
    "normalize_skill",
    "normalize_many",
    "extract_skills",
]
