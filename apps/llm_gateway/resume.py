"""Resume parsing orchestration (AI.md §3).

1. extract_text (raises UnreadablePdf on scanned / image-only / encrypted PDFs)
2. redact and assert_clean; on residual PII skip the LLM ("pii_residual")
3-5. cache, gateway call, rules fallback, validation (pipeline.run)
6. normalize_many(skills_raw)
7. map onto CandidateProfileUpdateSerializer fields; contacts from local redaction only
8. one structured log line (log_llm_call)
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any

from taxonomy import normalize_many

from . import pipeline
from .base import RESUME_PROMPT, Cache, LlmGateway
from .fake import FakeLlm
from .obs_logging import log_llm_call
from .pdf_text import extract_text
from .redact import assert_clean, redact
from .schema import validate_resume_payload
from .types import ResumeParseResult


def parse_resume(
    pdf_bytes: bytes,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> ResumeParseResult:
    """Orchestrate resume parsing end-to-end.

    Raises:
        UnreadablePdf: If the PDF cannot be read or contains no extractable text.
    """
    t0 = time.monotonic()
    raw_text = extract_text(pdf_bytes)
    redacted = redact(raw_text)
    is_clean, _ = assert_clean(redacted)

    from . import get_gateway
    active_gateway = gateway or get_gateway()

    outcome = pipeline.run(
        kind="resume",
        prompt_version=RESUME_PROMPT,
        redacted_text=redacted.text,
        is_clean=is_clean,
        gateway=active_gateway,
        cache=cache,
        call_llm=lambda: active_gateway.resume(redacted.text),
        call_rules=lambda: FakeLlm().resume(redacted.text),
        validate=validate_resume_payload,
    )
    draft = outcome.draft
    if outcome.fallback_reason == "pii_residual":
        # Something personal survived redaction: never copy free text into a profile that
        # employers see before an accepted offer (the candidate types it in the form instead)
        draft = dataclasses.replace(draft, about=None, experience_text=None)

    matches, unknown_terms = normalize_many(draft.skills_raw)

    # Keys of CandidateProfileUpdateSerializer (AI-R11). Unknown: "" for strings (the model's
    # CharFields are blank=True, not null=True), [] for lists, None for numbers.
    prefill: dict[str, Any] = {
        "city": draft.city or "",
        "specialization": draft.specialization or "",
        "claimed_grade": draft.claimed_grade or "",
        "years_experience": draft.years_experience,
        "roles": draft.roles,
        "work_formats": draft.work_formats,
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type or "",
        "about": draft.about or "",
        "experience_text": draft.experience_text or "",
        "skills": [m.skill_id for m in matches],
    }

    def first(kind: str) -> str | None:
        values = redacted.found.get(kind) or []
        return values[0] if values else None

    contacts = {
        "full_name": redacted.full_name,
        "email": first("email"),
        "phone": first("phone"),
        "telegram": first("telegram"),
    }

    log_llm_call(
        kind="resume",
        provider=active_gateway.name,
        model=outcome.model,
        prompt_version=RESUME_PROMPT,
        input_sha12=outcome.input_sha12,
        latency_ms=(time.monotonic() - t0) * 1000,
        cache_hit=outcome.cache_hit,
        source=outcome.source,
        fallback_reason=outcome.fallback_reason,
    )

    return ResumeParseResult(
        prefill=prefill,
        contacts=contacts,
        unknown_terms=unknown_terms,
        source=outcome.source,
        fallback_reason=outcome.fallback_reason,
    )
