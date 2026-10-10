"""Tests for Celery tasks, domain event publishing, and SSE streaming."""

from datetime import timedelta

import pytest
from core.enums import ContactChannel, OfferStatus, SalaryType
from django.conf import settings
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember, Position
from outreach.events import publish_domain_event, register_subscriber, unregister_subscriber
from outreach.models import Offer
from outreach.tasks import expire_offers
from profiles.models import CandidateProfile
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestCeleryAndEvents:
    def setup_method(self):
        self.client = APIClient()
        self.employer_user = User.objects.create_user(
            email="employer_celery@example.com",
            password="testpassword123",
            role="employer",
        )
        self.company = Company.objects.create(name="Celery Corp", inn="7701234567")
        CompanyMember.objects.create(user=self.employer_user, company=self.company)

        self.candidate_user = User.objects.create_user(
            email="candidate_celery@example.com",
            password="testpassword123",
            role="candidate",
        )
        self.candidate_profile = CandidateProfile.objects.create(
            user=self.candidate_user,
            specialization="backend",
            claimed_grade="middle",
        )
        self.position = Position.objects.create(
            company=self.company,
            title="Backend Dev",
            specialization="backend",
            grades=["middle"],
            salary_min=150000,
            salary_max=250000,
            salary_type=SalaryType.GROSS,
        )

    def test_celery_settings_configured(self):
        """CELERY_BEAT_SCHEDULE and CELERY_TASK_ROUTES are properly configured."""
        assert "expire-stale-offers" in settings.CELERY_BEAT_SCHEDULE
        schedule_item = settings.CELERY_BEAT_SCHEDULE["expire-stale-offers"]
        assert schedule_item["task"] == "outreach.tasks.expire_offers"
        assert schedule_item["schedule"] > 0

        assert "llm_gateway.*" in settings.CELERY_TASK_ROUTES
        assert settings.CELERY_TASK_ROUTES["llm_gateway.*"]["queue"] == "llm"

    def test_expire_offers_task(self):
        """expire_offers Celery task transitions expired pending offers."""
        now = timezone.now()
        past = now - timedelta(days=2)
        future = now + timedelta(days=7)

        expired_offer = Offer.objects.create(
            company=self.company,
            candidate=self.candidate_user,
            position=self.position,
            title="Backend Offer",
            description="Join us as backend engineer",
            salary_min=180000,
            salary_max=220000,
            salary_type=SalaryType.GROSS,
            contact_channel=ContactChannel.TELEGRAM,
            contact_value="@candidate",
            status=OfferStatus.SENT,
            expires_at=past,
        )
        active_offer = Offer.objects.create(
            company=self.company,
            candidate=self.candidate_user,
            position=self.position,
            title="Backend Offer 2",
            description="Join us as senior backend engineer",
            salary_min=200000,
            salary_max=250000,
            salary_type=SalaryType.GROSS,
            contact_channel=ContactChannel.TELEGRAM,
            contact_value="@candidate",
            status=OfferStatus.SENT,
            expires_at=future,
        )

        expired_count = expire_offers()
        assert expired_count == 1

        expired_offer.refresh_from_db()
        active_offer.refresh_from_db()
        assert expired_offer.status == OfferStatus.EXPIRED
        assert active_offer.status == OfferStatus.SENT

    def test_publish_and_receive_domain_event(self, django_capture_on_commit_callbacks):
        """A scoped subscriber receives its own events after commit."""
        queue = register_subscriber(user_id=self.candidate_user.id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                publish_domain_event(
                    "test.event", {"candidate_id": str(self.candidate_user.id), "hello": "world"}
                )
                assert queue.empty()  # not before commit
            assert not queue.empty()
            event = queue.get_nowait()
            assert event["event"] == "test.event"
            assert event["data"] == {"candidate_id": str(self.candidate_user.id), "hello": "world"}
            assert "timestamp" in event
        finally:
            unregister_subscriber(queue)

    def test_sse_endpoint_streaming(self, django_capture_on_commit_callbacks):
        """GET /api/events streams the employer's own company events only."""
        from outreach.events import _RECENT_EVENTS

        _RECENT_EVENTS.clear()

        self.client.force_authenticate(user=self.employer_user)

        with django_capture_on_commit_callbacks(execute=True):
            publish_domain_event(
                "offer.created", {"offer_id": 42, "company_id": str(self.company.id)}
            )
            publish_domain_event(
                "offer.created", {"offer_id": 43}
            )  # no audience: delivered to nobody

        response = self.client.get("/api/events?limit=2")
        assert response.status_code == 200
        assert "text/event-stream" in response["Content-Type"]

        content = b"".join(response.streaming_content).decode("utf-8")
        assert "event: offer.created" in content
        assert '"offer_id": 42' in content
        assert '"offer_id": 43' not in content
        _RECENT_EVENTS.clear()
