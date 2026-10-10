"""Tests for R14: FSP sync service improvements."""

from datetime import date
from unittest.mock import patch

import pytest
from assessment.models import LeagueMembership
from core.enums import Discipline, Grade, Specialization, SyncStatus, UserRole
from django.conf import settings
from fsp_sync.models import FSPLink, FSPResult
from fsp_sync.services import recompute_strength, sync_fsp_data
from fsp_sync.tasks import sync_all_fsp_profiles
from identity.models import User


@pytest.fixture
def candidate_user(db):
    return User.objects.create_user(
        email="candidate_fsp@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
    )


@pytest.mark.django_db
class TestFSPSyncServices:
    def test_sync_fsp_data_deletes_removed_results(self, candidate_user):
        link = FSPLink.objects.create(
            candidate=candidate_user,
            participant_id="FSP-TEST-001",
            sync_status=SyncStatus.PENDING,
        )
        # Create an existing result that won't be returned in registry next time
        FSPResult.objects.create(
            candidate=candidate_user,
            event_id="OLD-EVENT-999",
            event_name="Old Event",
            discipline=Discipline.ALGORITHMIC,
            date=date(2024, 1, 1),
            placement=1,
            tier="winner",
            participants_total=50,
            source_hash="dummy_hash",
        )
        assert candidate_user.fsp_results.count() == 1

        mock_data = {
            "sports_rank": "kms",
            "results": [
                {
                    "event_id": "NEW-EVENT-100",
                    "event_name": "New Event",
                    "discipline": Discipline.ALGORITHMIC,
                    "date": "2025-05-01",
                    "placement": 2,
                    "tier": "prize_winner",
                    "participants_total": 80,
                }
            ],
        }

        with patch("fsp_sync.services.get_registry_data", return_value=mock_data):
            updated_link = sync_fsp_data(candidate_user, link)

        assert updated_link.sync_status == SyncStatus.OK
        # OLD-EVENT-999 should be deleted, only NEW-EVENT-100 remains
        results = list(candidate_user.fsp_results.values_list("event_id", flat=True))
        assert results == ["NEW-EVENT-100"]

    def test_sync_fsp_data_registry_miss_sets_not_found_keeps_results(self, candidate_user):
        link = FSPLink.objects.create(
            candidate=candidate_user,
            participant_id="FSP-UNKNOWN",
            sync_status=SyncStatus.OK,
        )
        existing_res = FSPResult.objects.create(
            candidate=candidate_user,
            event_id="EXISTING-EVENT",
            event_name="Existing Event",
            discipline=Discipline.PRODUCT,
            date=date(2025, 2, 2),
            placement=3,
            tier="finalist",
            participants_total=30,
            source_hash="dummy_hash_2",
        )

        with patch("fsp_sync.services.get_registry_data", return_value={}):
            updated_link = sync_fsp_data(candidate_user, link)

        assert updated_link.sync_status in (SyncStatus.NOT_FOUND, SyncStatus.FAILED)
        assert updated_link.last_sync_at is not None
        # Existing results must be kept
        assert candidate_user.fsp_results.filter(id=existing_res.id).exists()

    def test_recompute_strength_uses_base_strength(self, candidate_user):
        lm = LeagueMembership.objects.create(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            base_strength=60.0,
            strength=60.0,
        )
        FSPResult.objects.create(
            candidate=candidate_user,
            event_id="EV1",
            event_name="E1",
            discipline=Discipline.ALGORITHMIC,
            date=date(2025, 1, 1),
            placement=1,
            tier="winner",
            participants_total=10,
            source_hash="h1",
        )
        recompute_strength(candidate_user)
        lm.refresh_from_db()
        assert lm.fsp_boost == 5.0
        assert lm.strength == 65.0
        assert lm.base_strength == 60.0

    def test_sync_all_fsp_profiles_task_returns_ok_and_failed(self, candidate_user):
        link = FSPLink.objects.create(
            candidate=candidate_user,
            participant_id="FSP-TASK-1",
            sync_status=SyncStatus.PENDING,
        )

        with patch("fsp_sync.tasks.sync_candidate_fsp_data", return_value=link):
            res = sync_all_fsp_profiles.run()

        assert "ok" in res
        assert "failed" in res
        assert "FSP-TASK-1" in res["ok"]

    def test_celery_beat_schedule_includes_sync_all_fsp_profiles(self):
        schedule = settings.CELERY_BEAT_SCHEDULE
        task_names = [entry.get("task") for entry in schedule.values()]
        assert "fsp_sync.tasks.sync_all_fsp_profiles" in task_names
