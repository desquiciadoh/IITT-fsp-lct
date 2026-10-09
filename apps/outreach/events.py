"""Event publishing and streaming utilities for domain events.

Events:
- offer.created
- offer.updated
- league.updated
- fsp.synced

Delivery is tenant-scoped and fails closed. The audience is derived from the
payload: a subscriber receives an event only when ``payload['candidate_id']``
is the subscriber's user id, or ``payload['company_id']`` is one of the
subscriber's companies. Events carrying neither key are delivered to nobody.

Events are dispatched on transaction commit, so rolled-back work never emits.

Follow-up: Redis publish is fire-and-forget only; there is no Redis
subscriber yet, so the SSE stream only sees events from the same process.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
# queue -> audience of that subscriber
_LOCAL_EVENT_SUBSCRIBERS: dict[queue.Queue, _Audience] = {}
# Ring buffer for replay on (re)connect; each entry is filtered per subscriber.
_RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=100)


@dataclass(frozen=True)
class _Audience:
    user_id: str | None
    company_ids: frozenset[str]

    def accepts(self, message: dict[str, Any]) -> bool:
        data = message.get('data')
        if not isinstance(data, dict):
            return False
        candidate_id = data.get('candidate_id')
        if self.user_id is not None and candidate_id is not None and str(candidate_id) == self.user_id:
            return True
        company_id = data.get('company_id')
        return company_id is not None and str(company_id) in self.company_ids


def register_subscriber(
    user_id: Any = None,
    company_ids: Iterable[Any] = (),
    replay_recent: bool = False,
) -> queue.Queue:
    """Register an in-memory queue subscriber scoped to a user and their companies.

    A subscriber without a user id and companies receives nothing.
    """
    audience = _Audience(
        user_id=str(user_id) if user_id is not None else None,
        company_ids=frozenset(str(c) for c in company_ids),
    )
    q: queue.Queue = queue.Queue(maxsize=100)
    with _LOCK:
        if replay_recent:
            for ev in _RECENT_EVENTS:
                if not audience.accepts(ev):
                    continue
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    break
        _LOCAL_EVENT_SUBSCRIBERS[q] = audience
    return q


def unregister_subscriber(q: queue.Queue) -> None:
    """Unregister an in-memory queue subscriber."""
    with _LOCK:
        _LOCAL_EVENT_SUBSCRIBERS.pop(q, None)


def _dispatch(message: dict[str, Any]) -> None:
    raw = json.dumps(message, default=str)

    # 1. Publish to Redis if available
    try:
        import redis
        broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
        if broker_url.startswith('redis://'):
            r = redis.from_url(broker_url, socket_timeout=0.5)
            r.publish('fsp_events', raw)
    except Exception as exc:
        logger.debug("Redis publish skipped: %s", exc)

    # 2. Buffer for replay and distribute to matching in-memory subscribers
    with _LOCK:
        _RECENT_EVENTS.append(message)
        subscribers = list(_LOCAL_EVENT_SUBSCRIBERS.items())
    for q, audience in subscribers:
        if not audience.accepts(message):
            continue
        try:
            q.put_nowait(message)
        except queue.Full:
            logger.warning("SSE subscriber queue full; dropping %s", message.get('event'))


def publish_domain_event(event_type: str, payload: dict[str, Any]) -> None:
    """Publish a domain event once the current transaction commits.

    Args:
        event_type: The event name (e.g. 'offer.created', 'offer.updated')
        payload: Event data; must carry 'candidate_id' and/or 'company_id'
            to reach anyone.
    """
    if 'candidate_id' not in payload and 'company_id' not in payload:
        logger.warning("Domain event %s has no audience keys; it will not be delivered", event_type)
    message = {
        'event': event_type,
        'data': dict(payload),
        'timestamp': time.time(),
    }
    transaction.on_commit(lambda: _dispatch(message))
