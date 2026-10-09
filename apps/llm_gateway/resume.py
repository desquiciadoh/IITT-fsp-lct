"""Resume parsing orchestration module.

Follows AI.md §3 workflow:
1. extract_text
2. redact
3. cache check
4. gateway.resume() with FakeLlm fallback
5. normalize_many(skills_raw)
6. map to CandidateProfileUpdateSerializer keys and return ResumeParseResult
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from apps.taxonomy import normalize_many
from .base import Cache, LlmGateway
from .fake import FakeLlm
from .pdf_text import extract_text
from .redact import redact
from .types import ResumeDraft, ResumeParseResult, Source, UnreadablePdf

logger = logging.getLogger(__name__)

RESUME_PROMPT_VERSION = "v1"


def _make_cache_key(prompt_version: str, text: str) -> str:
    h = hashlib.sha256(f"{prompt_version}:{text}".encode("utf-8")).hexdigest()
    return f"llm:resume:{h}"


def parse_resume(
    pdf_bytes: bytes,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> ResumeParseResult:
    """Orchestrate resume parsing end-to-end.

    Args:
        pdf_bytes: Raw bytes of uploaded PDF.
        gateway: LlmGateway implementation (defaults to FakeLlm if None or on error).
        cache: Optional cache implementation.

    Returns:
        ResumeParseResult matching CandidateProfileUpdateSerializer schema.

    Raises:
        UnreadablePdf: If the PDF cannot be read or contains no extractable text.
    """
    # 1. Extract text
    raw_text = extract_text(pdf_bytes)

    # 2. Local PII redaction (152-FZ)
    redacted = redact(raw_text)

    # Prepare gateway
    from . import get_gateway
    active_gateway = gateway or get_gateway()
    source: Source = "llm" if active_gateway.name != "fake" else "rules"

    # 3. Check Cache
    cache_key = _make_cache_key(RESUME_PROMPT_VERSION, redacted.text)
    draft_dict: dict[str, Any] | None = None

    if cache is not None:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                draft_dict = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                source = "llm"
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

    draft: ResumeDraft | None = None
    if draft_dict is not None:
        try:
            draft = ResumeDraft(**draft_dict)
        except Exception:
            draft = None

    # 4. Call gateway if not in cache
    if draft is None:
        try:
            draft = active_gateway.resume(redacted.text)
            # Store in cache if LLM call succeeded and cache provided
            if cache is not None and active_gateway.name != "fake":
                try:
                    cache_payload = {
                        "specialization": draft.specialization,
                        "claimed_grade": draft.claimed_grade,
                        "years_experience": draft.years_experience,
                        "roles": draft.roles,
                        "skills_raw": draft.skills_raw,
                        "work_formats": draft.work_formats,
                        "salary_min": draft.salary_min,
                        "salary_max": draft.salary_max,
                        "salary_type": draft.salary_type,
                        "city": draft.city,
                        "about": draft.about,
                        "experience_text": draft.experience_text,
                    }
                    cache.set(cache_key, json.dumps(cache_payload), ttl=7 * 86400)
                except Exception as e:
                    logger.warning(f"Cache set error: {e}")
        except Exception as e:
            logger.warning(f"Gateway {active_gateway.name} failed ({e}), falling back to FakeLlm")
            draft = FakeLlm().resume(redacted.text)
            source = "rules"

    # 5. Normalize skills against taxonomy
    matches, unknown_terms = normalize_many(draft.skills_raw)
    normalized_skill_ids = [m.skill_id for m in matches]

    # 6. Map onto CandidateProfileUpdateSerializer keys
    prefill: dict[str, Any] = {
        "city": draft.city,
        "specialization": draft.specialization,
        "claimed_grade": draft.claimed_grade,
        "years_experience": draft.years_experience,
        "roles": draft.roles,
        "work_formats": draft.work_formats,
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type,
        "about": draft.about,
        "experience_text": draft.experience_text,
        "skills": normalized_skill_ids,
    }

    # Extract contacts from local redaction only
    contacts = {
        "full_name": redacted.found.get("name", [None])[0] if redacted.found.get("name") else None,
        "email": redacted.found.get("email", [None])[0] if redacted.found.get("email") else None,
        "phone": redacted.found.get("phone", [None])[0] if redacted.found.get("phone") else None,
        "telegram": redacted.found.get("telegram", [None])[0] if redacted.found.get("telegram") else None,
    }

    return ResumeParseResult(
        prefill=prefill,
        contacts=contacts,
        unknown_terms=unknown_terms,
        source=source,
    )
