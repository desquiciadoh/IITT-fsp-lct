"""Job description parsing orchestration (AI.md §3).

1. redact recruiter contacts (no header heuristic: a title is not a name) and assert_clean
2-4. cache, gateway call, rules fallback, validation (pipeline.run)
5. normalize_many() for must and nice skills
6. map onto PositionSerializer writable fields
7. ML's blueprint_for(spec, skill_ids) when the specialization is known (AI-R13)
8. one structured log line (log_llm_call)
"""
from __future__ import annotations

import logging
import time
from typing import Any

from taxonomy import normalize_many

from . import pipeline
from .base import JD_PROMPT, Cache, LlmGateway
from .fake import FakeLlm
from .obs_logging import log_llm_call
from .redact import assert_clean, redact
from .schema import validate_jd_payload
from .types import JdParseResult

logger = logging.getLogger(__name__)


def parse_jd(
    text: str,
    *,
    gateway: LlmGateway | None = None,
    cache: Cache | None = None,
) -> JdParseResult:
    """Orchestrate vacancy JD parsing end-to-end."""
    t0 = time.monotonic()
    redacted = redact(text or "", header_names=False)
    is_clean, _ = assert_clean(redacted)

    from . import get_gateway
    active_gateway = gateway or get_gateway()

    outcome = pipeline.run(
        kind="jd",
        prompt_version=JD_PROMPT,
        redacted_text=redacted.text,
        is_clean=is_clean,
        gateway=active_gateway,
        cache=cache,
        call_llm=lambda: active_gateway.jd(redacted.text),
        call_rules=lambda: FakeLlm().jd(redacted.text),
        validate=validate_jd_payload,
    )
    draft = outcome.draft

    must_matches, must_unknown = normalize_many(draft.must_skills_raw)
    nice_matches, nice_unknown = normalize_many(draft.nice_skills_raw)
    must_skill_ids = [m.skill_id for m in must_matches]
    nice_skill_ids = [m.skill_id for m in nice_matches if m.skill_id not in must_skill_ids]

    # Writable keys of PositionSerializer (AI-R11)
    draft_payload: dict[str, Any] = {
        "title": draft.title or "",
        "specialization": draft.specialization,
        "grades": draft.grades,
        "must_skills": must_skill_ids,
        "nice_skills": nice_skill_ids,
        "work_formats": draft.work_formats,
        "location": draft.location or "",
        "salary_min": draft.salary_min,
        "salary_max": draft.salary_max,
        "salary_type": draft.salary_type,
        "team_context": draft.team_context or "",
        "description": draft.description or "",
    }

    blueprint, blueprint_failed = _blueprint(draft.specialization, must_skill_ids + nice_skill_ids)

    reason = outcome.fallback_reason
    if blueprint_failed:
        reason = f"{reason}+blueprint" if reason else "blueprint"
    log_llm_call(
        kind="jd",
        provider=active_gateway.name,
        model=outcome.model,
        prompt_version=JD_PROMPT,
        input_sha12=outcome.input_sha12,
        latency_ms=(time.monotonic() - t0) * 1000,
        cache_hit=outcome.cache_hit,
        source=outcome.source,
        fallback_reason=reason,
    )

    return JdParseResult(
        draft=draft_payload,
        unknown_terms=list(dict.fromkeys(must_unknown + nice_unknown)),
        blueprint=blueprint,
        source=outcome.source,
        fallback_reason=outcome.fallback_reason,
    )


def _blueprint(specialization: str | None, skill_ids: list[str]) -> tuple[list[dict[str, Any]], bool]:
    """ML's blueprint as [{"topic", "weight"}]; ([], True) if ML's function failed (AI-R13)."""
    if not specialization:
        return [], False
    try:
        from assessment.engine.blueprint import blueprint_for
    except ModuleNotFoundError as e:
        if (e.name or "").startswith("assessment.engine"):
            return [], False  # expected until ML-2 lands
        logger.error("blueprint_for import failed: %s", type(e).__name__)
        return [], True
    except ImportError as e:  # the module exists but does not export blueprint_for
        logger.error("blueprint_for import failed: %s", type(e).__name__)
        return [], True
    try:
        raw = blueprint_for(specialization, skill_ids)
        blueprint: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                blueprint.append({"topic": str(item["topic"]), "weight": float(item["weight"])})
            else:
                topic, weight = item
                blueprint.append({"topic": str(topic), "weight": float(weight)})
        return blueprint, False
    except Exception as e:
        logger.error("blueprint_for failed: %s", type(e).__name__)
        return [], True
