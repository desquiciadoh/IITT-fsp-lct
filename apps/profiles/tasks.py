from __future__ import annotations

import dataclasses
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="llm_gateway.parse_resume", queue="llm")
def parse_resume_task(pdf_bytes: bytes) -> dict:
    """Celery task to parse a resume PDF in the llm worker pool."""
    try:
        from llm_gateway import parse_resume
    except ImportError:
        logger.warning("llm_gateway package is not available")
        raise

    result = parse_resume(pdf_bytes)
    return dataclasses.asdict(result)
