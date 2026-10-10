import re
from unittest.mock import patch

import pytest
from assessment.models import LeagueMembership
from core.enums import Grade, LeagueStatus, SalaryType, Specialization, UserRole
from django.utils import timezone
from identity.models import User
from matching.serializers import TalentShortSerializer
from profiles.models import CandidateProfile, generate_public_id
from profiles.serializers import CandidateProfileSerializer


@pytest.mark.django_db
class TestPublicIdAndLeagueOrderingR19:
    def test_public_id_format_has_at_least_8_hex_chars(self):
        pid = generate_public_id()
        assert pid.startswith("C-")
        hex_part = pid[2:]
        assert len(hex_part) >= 8
        assert re.fullmatch(r"[0-9A-F]{8,}", hex_part) is not None

    def test_generate_public_id_retry_on_collision(self):
        user = User.objects.create_user(
            email="cand_coll1@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        existing_profile = CandidateProfile.objects.create(
            user=user,
            public_id="C-ABCDEF01",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )

        # Mock uuid.uuid4 to return a colliding hex first, then a fresh one
        class MockUUID:
            def __init__(self, hex_val):
                self.hex = hex_val

        call_count = 0

        def fake_uuid4():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MockUUID("abcdef019999")  # Collision with existing
            return MockUUID("123456789999")  # Fresh

        with patch("profiles.models.uuid.uuid4", side_effect=fake_uuid4):
            new_pid = generate_public_id(max_retries=5)
            assert new_pid == "C-12345678"
            assert new_pid != existing_profile.public_id
            assert call_count == 2

    def test_candidate_profile_save_retries_on_collision(self):
        user1 = User.objects.create_user(
            email="cand_coll2@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        profile1 = CandidateProfile.objects.create(
            user=user1,
            public_id="C-DEADBEEF",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )

        user2 = User.objects.create_user(
            email="cand_coll3@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        # Attempt to save with same public_id during create
        profile2 = CandidateProfile(
            user=user2,
            public_id="C-DEADBEEF",
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )
        profile2.save()
        assert profile2.public_id != profile1.public_id
        assert profile2.public_id.startswith("C-")
        assert len(profile2.public_id[2:]) >= 8

    def test_league_membership_meta_ordering_prefers_confirmed_over_unconfirmed(self):
        user = User.objects.create_user(
            email="cand_lm_ord@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        # Create unconfirmed membership first
        LeagueMembership.objects.create(
            candidate=user,
            specialization=Specialization.FRONTEND,
            grade=Grade.JUNIOR,
            status=LeagueStatus.UNCONFIRMED,
            confirmed_at=None,
        )
        # Create confirmed membership later
        lm_confirmed = LeagueMembership.objects.create(
            candidate=user,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
            confirmed_at=timezone.now(),
        )

        # .first() relying on Meta.ordering should return the confirmed membership
        first_lm = user.league_memberships.first()
        assert first_lm.id == lm_confirmed.id

    def test_league_membership_first_filters_by_specialization(self):
        user = User.objects.create_user(
            email="cand_spec_filter@example.com",
            password="password123",
            role=UserRole.CANDIDATE,
        )
        LeagueMembership.objects.create(
            candidate=user,
            specialization=Specialization.BACKEND,
            grade=Grade.SENIOR,
            status=LeagueStatus.CONFIRMED,
            confirmed_at=timezone.now(),
        )
        LeagueMembership.objects.create(
            candidate=user,
            specialization=Specialization.FRONTEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
            confirmed_at=timezone.now(),
        )

        # Profile with specialization FRONTEND
        profile = CandidateProfile.objects.create(
            user=user,
            public_id="C-FEEDFACE",
            specialization=Specialization.FRONTEND,
            salary_min=100000,
            salary_max=150000,
            salary_type=SalaryType.GROSS,
        )

        # CandidateProfileSerializer.get_league should pick FRONTEND
        prof_serializer = CandidateProfileSerializer(profile)
        assert prof_serializer.data["league"]["specialization"] == Specialization.FRONTEND
        assert prof_serializer.data["league"]["grade"] == Grade.MIDDLE

        # TalentShortSerializer.get_league should also pick FRONTEND
        talent_serializer = TalentShortSerializer(profile)
        assert talent_serializer.data["league"]["specialization"] == Specialization.FRONTEND
        assert talent_serializer.data["league"]["grade"] == Grade.MIDDLE
