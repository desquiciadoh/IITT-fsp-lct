"""Job Description (JD) parsing orchestration module.

Follows AI.md §3 workflow:
1. redact contact details and assert_clean(redacted)
2. cache check keyed by sha256(kind|prompt_version|model|redacted_text)
3. gateway.jd() with FakeLlm fallback (never caching rules output)
4. validate_jd_payload() on result
5. normalize_many() for must_skills and nice_skills
6. map to PositionSerializer writable keys (unknown text -> "", lists -> [], numbers -> None)
7. call ML's blueprint_for(spec, skills) safely (AI-R13)
8. log_llm_call() structured observability (AI-R12)
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
from .redact import assert_clean, redact
from .schema import validate_jd_payload
from .types import JdDraft, JdParseResult, Source

logger = logging.getLogger(__name__)

JD_PROMPT_VERSION = "jd.v1"


def _make_cache_key(kind: str, prompt_version: str, model: str, text: str) -> str:
    raw = f"{kind}|{prompt_version}|{model}|{text}".encode("utf-8")
    return f"llm:cache:{hashlib.sha256(raw).hexdigest()}"


def parse_jd(
    text: str,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> JdParseResult:
    """Orchestrate vacancy JD parsing end-to-end.

    Args:
        text: Vacancy description text.
        gateway: LlmGateway implementation (defaults to process-wide gateway or FakeLlm).
        cache: Optional cache implementation.

    Returns:
        JdParseResult matching PositionSerializer writable fields.
    """
    t0 = time.monotonic()
    if not text or not text.strip():
        text = ""

    # 1. Redact contacts from JD and verify cleanliness (no header heuristic: titles are not names)
    redacted = redact(text, header_names=False)
    is_clean, pii_residual = assert_clean(redacted)

    from . import get_gateway
    active_gateway = gateway or get_gateway()
    model_name = getattr(getattr(active_gateway, "config", None), "model", "default")
    cache_key = _make_cache_key("jd", JD_PROMPT_VERSION, model_name, redacted.text)
    input_sha12 = hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()[:12]

    source: Source = "rules" if active_gateway.name == "fake" else "llm"
    fallback_reason: str | None = None
    cache_hit = False
    draft: JdDraft | None = None

    if not is_clean:
        logger.warning(f"Residual PII detected in JD ({pii_residual}). Skipping LLM call.")
        fallback_reason = "pii_residual"
        source = "rules"
        draft = FakeLlm().jd(redacted.text)

    # 2. Check Cache
    if draft is None and cache is not None:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_obj = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                if isinstance(cached_obj, dict) and cached_obj.get("source") == "llm":
                    draft = validate_jd_payload(cached_obj.get("draft", {}))
                    source = "llm"
                    cache_hit = True
                    fallback_reason = None
        except Exception as e:
            logger.warning(f"Cache get error: {type(e).__name__}")
            draft = None

    # 3. Call Gateway if not cached
    if draft is None:
        if active_gateway.name == "fake":
            source = "rules"
            draft = FakeLlm().jd(redacted.text)
        else:
            try:
                draft = active_gateway.jd(redacted.text)
                source = "llm"
                fallback_reason = None

                # Store ONLY validated LLM result in cache
                if cache is not None:
                    try:
                        cache_entry = {
                            "v": 1,
                            "source": "llm",
                            "prompt": JD_PROMPT_VERSION,
                            "model": model_name,
                            "draft": {
                                "title": draft.title,
                                "specialization": draft.specialization,
                                "grades": draft.grades,
                                "must_skills_raw": draft.must_skills_raw,
                                "nice_skills_raw": draft.nice_skills_raw,
                                "work_formats": draft.work_formats,
                                "location": draft.location,
                                "salary_min": draft.salary_min,
                                "salary_max": draft.salary_max,
                                "salary_type": draft.salary_type,
                                "team_context": draft.team_context,
                                "description": draft.description,
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
                draft = FakeLlm().jd(redacted.text)
                source = "rules"
                fallback_reason = err_reason

    # 4. Normalize skills
    must_matches, must_unknown = normalize_many(draft.must_skills_raw)
    nice_matches, nice_unknown = normalize_many(draft.nice_skills_raw)

    must_skill_ids = [m.skill_id for m in must_matches]
    nice_skill_ids = [m.skill_id for m in nice_matches if m.skill_id not in must_skill_ids]
    all_unknown = list(dict.fromkeys(must_unknown + nice_unknown))

    # 5. Map onto PositionSerializer writable fields (AI-R11)
    draft_payload: dict[str, Any] = {
        "title": draft.title or "",
        "specialization": draft.specialization,
        "grades": draft.grades or [],
        "must_skills": must_skill_ids,
        "nice_skills": nice_skill_ids,
        "work_formats": draft.work_formats or [],
        "location": draft.location or "",
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type,
        "team_context": draft.team_context or "",
        "description": draft.description or "",
    }

    # 6. Call ML's blueprint_for if available (AI-R13)
    blueprint: list[dict[str, Any]] = []
    blueprint_failed = False
    if draft.specialization:
        try:
            from assessment.engine.blueprint import blueprint_for  # type: ignore
            all_skills = must_skill_ids + nice_skill_ids
            raw_bp = blueprint_for(draft.specialization, all_skills)
            if isinstance(raw_bp, list):
                for item in raw_bp:
                    if isinstance(item, (tuple, list)) and len(item) == 2:
                        blueprint.append({"topic": str(item[0]), "weight": float(item[1])})
                    elif isinstance(item, dict) and "topic" in item and "weight" in item:
                        blueprint.append({"topic": str(item["topic"]), "weight": float(item["weight"])})
        except ModuleNotFoundError:
            # Expected before ML module is merged
            blueprint = []
        except Exception as e:
            logger.error(f"Error calling blueprint_for: {type(e).__name__}: {e}")
            blueprint = []
            blueprint_failed = True

    # 7. Observability structured logging (AI-R12)
    latency_ms = int((time.monotonic() - t0) * 1000)
    extra_reason = fallback_reason
    if blueprint_failed:
        extra_reason = f"{extra_reason or ''}+blueprint" if extra_reason else "blueprint"

    log_llm_call(
        kind="jd",
        provider=active_gateway.name,
        model=model_name,
        prompt_version=JD_PROMPT_VERSION,
        input_sha12=input_sha12,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        source=source,
        fallback_reason=extra_reason,
    )

    return JdParseResult(
        draft=draft_payload,
        unknown_terms=all_unknown,
        blueprint=blueprint,
        source=source,
        fallback_reason=fallback_reason,
    )
