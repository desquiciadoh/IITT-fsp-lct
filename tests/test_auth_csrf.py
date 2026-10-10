"""Tests for CSRF protection on anonymous login, register, and demo/persona (R6)."""

import pytest
from core.enums import UserRole
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def csrf_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def test_user(db):
    return User.objects.create_user(
        email="test_csrf@example.com",
        password="secretpassword",
        role=UserRole.CANDIDATE,
    )


@pytest.mark.django_db
class TestLoginCSRF:
    def test_anonymous_login_without_csrf_is_rejected(self, csrf_client, test_user):
        res = csrf_client.post(
            "/api/auth/login",
            {"email": test_user.email, "password": "secretpassword"},
            format="json",
        )
        assert res.status_code == 403

    def test_anonymous_register_without_csrf_is_rejected(self, csrf_client):
        res = csrf_client.post(
            "/api/auth/register",
            {"email": "new_csrf@example.com", "password": "secretpassword", "role": "candidate"},
            format="json",
        )
        assert res.status_code == 403

    def test_demo_persona_without_csrf_is_rejected(self, csrf_client, settings):
        settings.DEMO_MODE = True
        res = csrf_client.post(
            "/api/demo/persona",
            {"persona": "candidate_plain"},
            format="json",
        )
        assert res.status_code == 403

    def test_login_with_valid_csrf_token_succeeds(self, csrf_client, test_user):
        # 1. Obtain CSRF cookie from /api/auth/csrf
        csrf_res = csrf_client.get("/api/auth/csrf")
        assert csrf_res.status_code == 204
        csrf_token = csrf_client.cookies.get("csrftoken").value
        assert csrf_token is not None

        # 2. Submit login with X-CSRFToken header
        res = csrf_client.post(
            "/api/auth/login",
            {"email": test_user.email, "password": "secretpassword"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert res.status_code == 200
        assert res.json()["email"] == test_user.email
