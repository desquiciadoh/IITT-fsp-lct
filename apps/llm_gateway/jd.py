"""Job Description (JD) parsing orchestration module.

Follows AI.md §3 workflow:
1. redact contact details
2. cache check
3. gateway.jd() with FakeLlm fallback
4. normalize_many() for must_skills and nice_skills
5. map to PositionSerializer writable keys
6. call ML's blueprint_for() if available
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from apps.taxonomy import normalize_many
from .base import Cache, LlmGateway
from .fake import FakeLlm
from .redact import redact
from .types import JdDraft, JdParseResult, Source

logger = logging.getLogger(__name__)

JD_PROMPT_VERSION = "v1"


def _make_cache_key(prompt_version: str, text: str) -> str:
    h = hashlib.sha256(f"{prompt_version}:{text}".encode("utf-8")).hexdigest()
    return f"llm:jd:{h}"


def parse_jd(
    text: str,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> JdParseResult:
    """Orchestrate vacancy JD parsing end-to-end.

    Args:
        text: Vacancy description text.
        gateway: LlmGateway implementation (defaults to FakeLlm if None or on error).
        cache: Optional cache implementation.

    Returns:
        JdParseResult matching PositionSerializer writable fields.
    """
    if not text or not text.strip():
        text = ""

    # 1. Redact contacts from JD
    redacted = redact(text)

    from . import get_gateway
    active_gateway = gateway or get_gateway()
    source: Source = "llm" if active_gateway.name != "fake" else "rules"

    # 2. Check Cache
    cache_key = _make_cache_key(JD_PROMPT_VERSION, redacted.text)
    draft_dict: dict[str, Any] | None = None

    if cache is not None:
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                draft_dict = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                source = "llm"
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

    draft: JdDraft | None = None
    if draft_dict is not None:
        try:
            draft = JdDraft(**draft_dict)
        except Exception:
            draft = None

    # 3. Call gateway if not cached
    if draft is None:
        try:
            draft = active_gateway.jd(redacted.text)
            if cache is not None and active_gateway.name != "fake":
                try:
                    cache_payload = {
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
                    }
                    cache.set(cache_key, json.dumps(cache_payload), ttl=7 * 86400)
                except Exception as e:
                    logger.warning(f"Cache set error: {e}")
        except Exception as e:
            logger.warning(f"Gateway {active_gateway.name} failed ({e}), falling back to FakeLlm")
            draft = FakeLlm().jd(redacted.text)
            source = "rules"

    # 4. Normalize skills
    must_matches, must_unknown = normalize_many(draft.must_skills_raw)
    nice_matches, nice_unknown = normalize_many(draft.nice_skills_raw)

    must_skill_ids = [m.skill_id for m in must_matches]
    nice_skill_ids = [m.skill_id for m in nice_matches if m.skill_id not in must_skill_ids]
    all_unknown = list(dict.fromkeys(must_unknown + nice_unknown))

    # 5. Map onto PositionSerializer writable fields
    draft_payload: dict[str, Any] = {
        "title": draft.title or "Software Engineer",
        "specialization": draft.specialization or "backend",
        "grades": draft.grades or ["middle"],
        "must_skills": must_skill_ids,
        "nice_skills": nice_skill_ids,
        "work_formats": draft.work_formats or ["remote"],
        "location": draft.location,
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type or "net",
        "team_context": draft.team_context,
        "description": draft.description,
    }

    # 6. Call ML's blueprint_for if available
    blueprint: list[dict[str, Any]] = []
    try:
        from apps.assessment.engine.blueprint import blueprint_for  # type: ignore
        all_skills = must_skill_ids + nice_skill_ids
        raw_bp = blueprint_for(draft.specialization, all_skills)
        if isinstance(raw_bp, list):
            for item in raw_bp:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    blueprint.append({"topic": str(item[0]), "weight": float(item[1])})
                elif isinstance(item, dict) and "topic" in item and "weight" in item:
                    blueprint.append(item)
    except (ImportError, Exception):
        blueprint = []

    return JdParseResult(
        draft=draft_payload,
        unknown_terms=all_unknown,
        blueprint=blueprint,
        source=source,
    )
