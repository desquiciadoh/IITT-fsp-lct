"""Event publishing and streaming utilities for domain events.

Events:
- offer.created
- offer.updated
- league.updated
- fsp.synced
"""
from __future__ import annotations

import json
import logging
import queue
import time
from collections import deque
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# In-memory event queue fallback and ring buffer for replay
_LOCAL_EVENT_SUBSCRIBERS: list[queue.Queue] = []
_RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=100)


def register_subscriber(replay_recent: bool = False) -> queue.Queue:
    """Register an in-memory queue subscriber."""
    q: queue.Queue = queue.Queue(maxsize=100)
    if replay_recent:
        for ev in list(_RECENT_EVENTS):
            try:
                q.put_nowait(ev)
            except queue.Full:
                break
    _LOCAL_EVENT_SUBSCRIBERS.append(q)
    return q


def unregister_subscriber(q: queue.Queue) -> None:
    """Unregister an in-memory queue subscriber."""
    if q in _LOCAL_EVENT_SUBSCRIBERS:
        _LOCAL_EVENT_SUBSCRIBERS.remove(q)


def publish_domain_event(event_type: str, payload: dict[str, Any]) -> None:
    """Publish a domain event to Redis pub/sub and in-memory subscribers.

    Args:
        event_type: The event name (e.g. 'offer.created', 'offer.updated')
        payload: Event data dictionary
    """
    message = {
        'event': event_type,
        'data': payload,
        'timestamp': time.time(),
    }
    _RECENT_EVENTS.append(message)
    raw = json.dumps(message)

    # 1. Publish to Redis if available
    try:
        import redis
        broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
        if broker_url.startswith('redis://'):
            r = redis.from_url(broker_url, socket_timeout=0.5)
            r.publish('fsp_events', raw)
    except Exception as exc:
        logger.debug("Redis publish skipped: %s", exc)

    # 2. Distribute to in-memory subscribers
    for q in list(_LOCAL_EVENT_SUBSCRIBERS):
        try:
            q.put_nowait(message)
        except queue.Full:
            pass
