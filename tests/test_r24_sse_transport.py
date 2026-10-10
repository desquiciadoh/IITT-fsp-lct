import pytest
from core.enums import UserRole
from django.test import override_settings
from identity.models import User
from outreach.events import (
    _SEEN_MSG_IDS,
    _handle_remote_message,
    publish_domain_event,
    register_subscriber,
    unregister_subscriber,
)
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestR24SSETransport:
    def test_remote_redis_message_delivered_to_scoped_subscriber(self):
        user = User.objects.create_user(
            email="cand@example.com", password="password123", role=UserRole.CANDIDATE
        )
        sub = register_subscriber(user_id=user.id)
        try:
            remote_msg = {
                "id": "remote-msg-1",
                "event": "offer.created",
                "data": {"candidate_id": str(user.id), "title": "Job Offer"},
                "timestamp": 1234567.0,
            }
            _handle_remote_message(remote_msg)

            assert not sub.empty()
            received = sub.get_nowait()
            assert received["id"] == "remote-msg-1"
            assert received["event"] == "offer.created"
            assert received["data"]["title"] == "Job Offer"
        finally:
            unregister_subscriber(sub)

    def test_duplicate_remote_message_is_ignored(self):
        user = User.objects.create_user(
            email="cand2@example.com", password="password123", role=UserRole.CANDIDATE
        )
        sub = register_subscriber(user_id=user.id)
        try:
            remote_msg = {
                "id": "dup-msg-1",
                "event": "league.updated",
                "data": {"candidate_id": str(user.id), "grade": "lead"},
                "timestamp": 1234567.0,
            }
            _handle_remote_message(remote_msg)
            assert sub.qsize() == 1

            # Second delivery with same id must be ignored
            _handle_remote_message(remote_msg)
            assert sub.qsize() == 1
        finally:
            unregister_subscriber(sub)

    def test_published_domain_event_has_unique_id(self, django_capture_on_commit_callbacks):
        user = User.objects.create_user(
            email="cand3@example.com", password="password123", role=UserRole.CANDIDATE
        )
        sub = register_subscriber(user_id=user.id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                publish_domain_event(
                    "league.updated", {"candidate_id": str(user.id), "grade": "senior"}
                )
            assert not sub.empty()
            item = sub.get_nowait()
            assert "id" in item
            assert item["id"] in _SEEN_MSG_IDS
        finally:
            unregister_subscriber(sub)

    @override_settings(SSE_ENABLED=False)
    def test_sse_disabled_returns_501(self):
        user = User.objects.create_user(
            email="cand4@example.com", password="password123", role=UserRole.CANDIDATE
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/events")
        assert response.status_code == 501
