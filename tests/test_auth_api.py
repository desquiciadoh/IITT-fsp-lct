"""Tests for Authentication, Email Verification, Demo Persona, Time Travel, and Reset (G1, G2, G4, B3, B25)."""
import pytest
from django.core import signing
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import User
from assessment.models import AssessmentSession, LeagueMembership
from core.enums import AssessmentStatus, Grade, LeagueStatus, Specialization, UserRole


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email='newcandidate@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
    )
    return user


@pytest.mark.django_db
class TestAuthAndVerification:

    def test_register_returns_verify_link_in_demo_mode(self, client, settings):
        settings.DEMO_MODE = True
        payload = {
            'email': 'demo_applicant@example.com',
            'password': 'password123',
            'role': 'candidate',
        }
        res = client.post('/api/auth/register', payload, format='json')
        assert res.status_code == 201
        data = res.json()
        assert data['email'] == 'demo_applicant@example.com'
        assert data['role'] == 'candidate'
        assert 'verify_link' in data
        assert '/verify-email?token=' in data['verify_link']

    def test_verify_email_success(self, client, candidate_user):
        assert candidate_user.email_verified_at is None
        token = signing.dumps({'user_id': str(candidate_user.id)}, salt='email-verify')

        res = client.post('/api/auth/verify-email', {'token': token}, format='json')
        assert res.status_code == 204

        candidate_user.refresh_from_db()
        assert candidate_user.email_verified_at is not None
        assert candidate_user.is_email_verified is True

    def test_verify_email_invalid_token(self, client):
        res = client.post('/api/auth/verify-email', {'token': 'invalid-token-123'}, format='json')
        assert res.status_code == 400
        assert res.json()['code'] == 'invalid_token'

    def test_verify_email_validation_missing_token(self, client):
        res = client.post('/api/auth/verify-email', {}, format='json')
        assert res.status_code == 422
        assert res.json()['code'] == 'validation_failed'


@pytest.mark.django_db
class TestDemoResetAndTimeTravel:

    def test_time_travel_success(self, client, candidate_user, settings):
        settings.DEMO_MODE = True
        client.force_authenticate(user=candidate_user)

        res = client.post('/api/demo/time-travel', {'days': 15}, format='json')
        assert res.status_code == 200
        assert res.json()['clock_offset_days'] == 15

        candidate_user.refresh_from_db()
        assert candidate_user.clock_offset_days == 15

    def test_time_travel_validation_boundaries(self, client, candidate_user, settings):
        settings.DEMO_MODE = True
        client.force_authenticate(user=candidate_user)

        # Negative days
        res = client.post('/api/demo/time-travel', {'days': -1}, format='json')
        assert res.status_code == 422

        # Too large
        res = client.post('/api/demo/time-travel', {'days': 500}, format='json')
        assert res.status_code == 422

        # Non-integer
        res = client.post('/api/demo/time-travel', {'days': 'abc'}, format='json')
        assert res.status_code == 422

    def test_demo_reset_clears_clock_offset_and_cooldowns(self, client, candidate_user, settings):
        settings.DEMO_MODE = True
        candidate_user.clock_offset_days = 25
        candidate_user.save()

        # Create active assessment session and cooldown membership
        session = AssessmentSession.objects.create(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            status=AssessmentStatus.IN_PROGRESS,
        )
        membership = LeagueMembership.objects.create(
            candidate=candidate_user,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.UNCONFIRMED,
            next_attempt_at=timezone.now() + timezone.timedelta(days=30),
        )

        client.force_authenticate(user=candidate_user)
        res = client.post('/api/demo/reset', format='json')
        assert res.status_code == 200
        assert res.json()['clock_offset_days'] == 0

        candidate_user.refresh_from_db()
        assert candidate_user.clock_offset_days == 0

        session.refresh_from_db()
        assert session.status == AssessmentStatus.ABANDONED

        membership.refresh_from_db()
        assert membership.next_attempt_at is None

    def test_demo_reset_disabled_when_demo_mode_false(self, client, candidate_user, settings):
        settings.DEMO_MODE = False
        client.force_authenticate(user=candidate_user)

        res = client.post('/api/demo/reset', format='json')
        assert res.status_code == 403
        assert res.json()['code'] == 'forbidden'
