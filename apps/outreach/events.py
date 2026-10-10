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
import uuid
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
_SEEN_MSG_IDS: deque[str] = deque(maxlen=500)

_REDIS_THREAD: threading.Thread | None = None
_STOP_REDIS_LISTENER = threading.Event()


@dataclass(frozen=True)
class _Audience:
    user_id: str | None
    company_ids: frozenset[str]

    def accepts(self, message: dict[str, Any]) -> bool:
        data = message.get("data")
        if not isinstance(data, dict):
            return False
        candidate_id = data.get("candidate_id")
        if (
            self.user_id is not None
            and candidate_id is not None
            and str(candidate_id) == self.user_id
        ):
            return True
        company_id = data.get("company_id")
        return company_id is not None and str(company_id) in self.company_ids


def register_subscriber(
    user_id: Any = None,
    company_ids: Iterable[Any] = (),
    replay_recent: bool = False,
) -> queue.Queue:
    """Register an in-memory queue subscriber scoped to a user and their companies.

    A subscriber without a user id and companies receives nothing.
    """
    ensure_redis_subscriber_started()
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


def _handle_remote_message(message: dict[str, Any]) -> None:
    msg_id = message.get("id")
    with _LOCK:
        if msg_id and msg_id in _SEEN_MSG_IDS:
            return
        if msg_id:
            _SEEN_MSG_IDS.append(msg_id)
        _RECENT_EVENTS.append(message)
        subscribers = list(_LOCAL_EVENT_SUBSCRIBERS.items())
    for q, audience in subscribers:
        if not audience.accepts(message):
            continue
        try:
            q.put_nowait(message)
        except queue.Full:
            logger.warning("SSE subscriber queue full; dropping %s", message.get("event"))


def _redis_listener_worker() -> None:
    broker_url = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "REDIS_URL", "")
    if not broker_url or not broker_url.startswith("redis://"):
        return

    try:
        import redis
    except ImportError:
        return

    while not _STOP_REDIS_LISTENER.is_set():
        try:
            r = redis.from_url(broker_url, socket_timeout=5.0)
            pubsub = r.pubsub()
            pubsub.subscribe("fsp_events")
            logger.info("Subscribed to Redis channel fsp_events")
            while not _STOP_REDIS_LISTENER.is_set():
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                try:
                    payload = json.loads(data)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    _handle_remote_message(payload)
        except Exception as exc:
            logger.debug("Redis subscriber error: %s; reconnecting in 2s", exc)
            time.sleep(2.0)


def ensure_redis_subscriber_started() -> None:
    global _REDIS_THREAD
    with _LOCK:
        if _REDIS_THREAD is not None and _REDIS_THREAD.is_alive():
            return
        broker_url = getattr(settings, "CELERY_BROKER_URL", "") or getattr(
            settings, "REDIS_URL", ""
        )
        if not broker_url or not broker_url.startswith("redis://"):
            return
        _STOP_REDIS_LISTENER.clear()
        _REDIS_THREAD = threading.Thread(
            target=_redis_listener_worker,
            daemon=True,
            name="fsp_events_subscriber",
        )
        _REDIS_THREAD.start()


def stop_redis_subscriber() -> None:
    global _REDIS_THREAD
    _STOP_REDIS_LISTENER.set()
    with _LOCK:
        if _REDIS_THREAD is not None and _REDIS_THREAD.is_alive():
            _REDIS_THREAD.join(timeout=1.0)
        _REDIS_THREAD = None


def _dispatch(message: dict[str, Any]) -> None:
    msg_id = message.get("id")
    with _LOCK:
        if msg_id:
            _SEEN_MSG_IDS.append(msg_id)
        _RECENT_EVENTS.append(message)
        subscribers = list(_LOCAL_EVENT_SUBSCRIBERS.items())
    for q, audience in subscribers:
        if not audience.accepts(message):
            continue
        try:
            q.put_nowait(message)
        except queue.Full:
            logger.warning("SSE subscriber queue full; dropping %s", message.get("event"))

    raw = json.dumps(message, default=str)

    # Publish to Redis if available
    try:
        import redis

        broker_url = getattr(settings, "CELERY_BROKER_URL", "") or getattr(
            settings, "REDIS_URL", ""
        )
        if broker_url and broker_url.startswith("redis://"):
            r = redis.from_url(broker_url, socket_timeout=0.5)
            r.publish("fsp_events", raw)
    except Exception as exc:
        logger.debug("Redis publish skipped: %s", exc)


def publish_domain_event(event_type: str, payload: dict[str, Any]) -> None:
    """Publish a domain event once the current transaction commits.

    Args:
        event_type: The event name (e.g. 'offer.created', 'offer.updated')
        payload: Event data; must carry 'candidate_id' and/or 'company_id'
            to reach anyone.
    """
    if "candidate_id" not in payload and "company_id" not in payload:
        logger.warning("Domain event %s has no audience keys; it will not be delivered", event_type)
    message = {
        "id": str(uuid.uuid4()),
        "event": event_type,
        "data": dict(payload),
        "timestamp": time.time(),
    }
    transaction.on_commit(lambda: _dispatch(message))
