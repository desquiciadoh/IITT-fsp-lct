"""Types and data contracts for the LLM Gateway.

Pure Python dataclasses matching AI.md specifications and BE serializer fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Source = Literal["llm", "rules"]


@dataclass(frozen=True)
class Redacted:
    """Result of PII redaction (152-FZ).

    Contains text with PII replaced by placeholders and local mapping of found PII.
    """
    text: str  # PII replaced with placeholders: [EMAIL], [PHONE], [NAME], [URL], [TG]
    found: dict[str, list[str]] = field(default_factory=lambda: {
        "email": [],
        "phone": [],
        "telegram": [],
        "url": [],
        "name": [],
    })
    full_name: str | None = None  # the candidate's own name (header or "ФИО:"), never a referee


@dataclass(frozen=True)
class ResumeDraft:
    """What the LLM or rules engine extracts from redacted resume text."""
    specialization: str | None = None
    claimed_grade: str | None = None
    years_experience: float | None = None
    roles: list[str] = field(default_factory=list)
    skills_raw: list[str] = field(default_factory=list)  # as written in the CV
    work_formats: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_type: str | None = None
    city: str | None = None
    about: str | None = None  # <= 500 chars, no PII
    experience_text: str | None = None


@dataclass(frozen=True)
class ResumeParseResult:
    """Full parsed resume payload ready for BE endpoints.

    prefill keys match CandidateProfileUpdateSerializer fields.
    """
    prefill: dict[str, Any]  # keys = CandidateProfileUpdateSerializer fields; "skills" = list of skill ids
    contacts: dict[str, Any]  # {"full_name", "email", "phone", "telegram"} from local redaction only
    unknown_terms: list[str]  # raw skills that normalize_skill() could not map
    source: Source
    # Why the rules answered: "provider_fake" | "no_key" | "pii_residual" | "timeout" | "http_error"
    # | "schema" | "error" (unexpected exception in the adapter); None when source == "llm"
    fallback_reason: str | None = None


@dataclass(frozen=True)
class JdDraft:
    """What the LLM or rules engine extracts from Job Description text."""
    title: str | None = None
    specialization: str | None = None
    grades: list[str] = field(default_factory=list)
    must_skills_raw: list[str] = field(default_factory=list)
    nice_skills_raw: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_type: str | None = None
    team_context: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class JdParseResult:
    """Full parsed JD payload ready for BE endpoints.

    draft keys match PositionSerializer writable fields.
    """
    draft: dict[str, Any]  # keys = PositionSerializer writable fields; skills as ids
    unknown_terms: list[str]
    blueprint: list[dict[str, Any]]  # [{"topic": str, "weight": float}] from ML's blueprint_for(); [] until available
    source: Source
    fallback_reason: str | None = None


class UnreadablePdf(Exception):
    """Raised when PDF cannot be read, is empty or scanned without extractable text."""
