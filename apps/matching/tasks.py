from __future__ import annotations

import dataclasses
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="llm_gateway.parse_jd", queue="llm")
def parse_jd_task(text: str) -> dict:
    """Celery task to parse a vacancy job description in the llm worker pool."""
    try:
        from llm_gateway import parse_jd
    except ImportError:
        logger.warning("llm_gateway package is not available")
        raise

    result = parse_jd(text)
    return dataclasses.asdict(result)
