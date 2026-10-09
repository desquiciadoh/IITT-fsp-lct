"""Resume parsing orchestration module.

Follows AI.md §3 workflow:
1. extract_text (raises UnreadablePdf on scanned / image-only / encrypted PDFs)
2. redact and assert_clean(redacted). On residual PII, skip LLM (reason="pii_residual")
3. cache check keyed by sha256(kind|prompt_version|model|redacted_text)
4. gateway.resume() with FakeLlm fallback on any error (never caching rules output)
5. validate_resume_payload() on result
6. normalize_many(skills_raw)
7. map to CandidateProfileUpdateSerializer (empty strings for unknown text, [] for lists, None for numbers)
8. log_llm_call() structured observability
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from taxonomy import normalize_many

from .base import Cache, LlmGateway
from .fake import FakeLlm
from .obs_logging import log_llm_call
from .pdf_text import extract_text
from .redact import assert_clean, redact
from .schema import validate_resume_payload
from .types import ResumeDraft, ResumeParseResult, Source

logger = logging.getLogger(__name__)

RESUME_PROMPT_VERSION = "resume.v2"


def _make_cache_key(kind: str, prompt_version: str, model: str, text: str) -> str:
    raw = f"{kind}|{prompt_version}|{model}|{text}".encode("utf-8")
    return f"llm:cache:{hashlib.sha256(raw).hexdigest()}"


def parse_resume(
    pdf_bytes: bytes,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> ResumeParseResult:
    """Orchestrate resume parsing end-to-end.

    Args:
        pdf_bytes: Raw bytes of uploaded PDF.
        gateway: LlmGateway implementation (defaults to process-wide gateway or FakeLlm).
        cache: Optional cache implementation.

    Returns:
        ResumeParseResult matching CandidateProfileUpdateSerializer schema.

    Raises:
        UnreadablePdf: If the PDF cannot be read or contains no extractable text.
    """
    t0 = time.monotonic()

    # 1. Extract text
    raw_text = extract_text(pdf_bytes)

    # 2. Local PII redaction and safety assertion
    redacted = redact(raw_text)
    is_clean, pii_residual = assert_clean(redacted)

    from . import get_gateway
    active_gateway = gateway or get_gateway()
    model_name = getattr(getattr(active_gateway, "config", None), "model", "default")
    cache_key = _make_cache_key("resume", RESUME_PROMPT_VERSION, model_name, redacted.text)
    input_sha12 = hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()[:12]

    source: Source = "rules" if active_gateway.name == "fake" else "llm"
    fallback_reason: str | None = None
    cache_hit = False
    draft: ResumeDraft | None = None

    if not is_clean:
        logger.warning(f"Residual PII detected ({pii_residual}). Skipping LLM call.")
        fallback_reason = "pii_residual"
        source = "rules"
        draft = FakeLlm().resume(redacted.text)

    # 3. Check Cache
    if draft is None and cache is not None:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_obj = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                if isinstance(cached_obj, dict) and cached_obj.get("source") == "llm":
                    draft = validate_resume_payload(cached_obj.get("draft", {}))
                    source = "llm"
                    cache_hit = True
                    fallback_reason = None
        except Exception as e:
            logger.warning(f"Cache get error: {type(e).__name__}")
            draft = None

    # 4. Call Gateway if not cached
    if draft is None:
        if active_gateway.name == "fake":
            source = "rules"
            draft = FakeLlm().resume(redacted.text)
        else:
            try:
                draft = active_gateway.resume(redacted.text)
                source = "llm"
                fallback_reason = None

                # Store ONLY validated LLM result in cache
                if cache is not None:
                    try:
                        cache_entry = {
                            "v": 1,
                            "source": "llm",
                            "prompt": RESUME_PROMPT_VERSION,
                            "model": model_name,
                            "draft": {
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
                            },
                        }
                        cache.set(cache_key, json.dumps(cache_entry), ttl=7 * 86400)
                    except Exception as e:
                        logger.warning(f"Cache set error: {type(e).__name__}")

            except Exception as e:
                err_reason = getattr(e, "reason", "http_error")
                if isinstance(e, TimeoutError):
                    err_reason = "timeout"
                logger.warning(f"Gateway {active_gateway.name} failed ({type(e).__name__}: {err_reason}), falling back to rules")
                draft = FakeLlm().resume(redacted.text)
                source = "rules"
                fallback_reason = err_reason

    # 5. Normalize skills
    matches, unknown_terms = normalize_many(draft.skills_raw)
    normalized_skill_ids = [m.skill_id for m in matches]

    # 6. Map onto CandidateProfileUpdateSerializer writable fields (AI-R11)
    prefill: dict[str, Any] = {
        "city": draft.city or "",
        "specialization": draft.specialization,
        "claimed_grade": draft.claimed_grade,
        "years_experience": draft.years_experience,
        "roles": draft.roles or [],
        "work_formats": draft.work_formats or [],
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type,
        "about": draft.about or "",
        "experience_text": draft.experience_text or "",
        "skills": normalized_skill_ids,
    }

    # 7. Contacts from local redaction only
    contacts = {
        "full_name": redacted.full_name,
        "email": redacted.found.get("email", [None])[0] if redacted.found.get("email") else None,
        "phone": redacted.found.get("phone", [None])[0] if redacted.found.get("phone") else None,
        "telegram": redacted.found.get("telegram", [None])[0] if redacted.found.get("telegram") else None,
    }

    # 8. Observability structured logging (AI-R12)
    latency_ms = int((time.monotonic() - t0) * 1000)
    log_llm_call(
        kind="resume",
        provider=active_gateway.name,
        model=model_name,
        prompt_version=RESUME_PROMPT_VERSION,
        input_sha12=input_sha12,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        source=source,
        fallback_reason=fallback_reason,
    )

    return ResumeParseResult(
        prefill=prefill,
        contacts=contacts,
        unknown_terms=unknown_terms,
        source=source,
        fallback_reason=fallback_reason,
    )
