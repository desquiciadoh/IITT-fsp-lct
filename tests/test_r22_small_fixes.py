import base64
import hashlib
import importlib
import json
from unittest.mock import patch

import pytest
from core.enums import UserRole
from django.apps import apps
from django.core import signing
from django.db import IntegrityError
from identity.models import Identity, User
from outreach.views import EventStreamRenderer
from rest_framework.response import Response
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestR22EventStreamRenderer:
    def test_renderer_renders_dict_as_json_and_sets_content_type(self):
        renderer = EventStreamRenderer()
        error_dict = {
            "type": "https://fsp-draft.local/problems/not_authenticated",
            "title": "Authentication required",
            "status": 401,
            "code": "not_authenticated",
        }
        response = Response(error_dict, status=401)
        rendered = renderer.render(error_dict, renderer_context={"response": response})
        assert isinstance(rendered, (bytes, str))
        decoded = json.loads(rendered)
        assert decoded["code"] == "not_authenticated"
        assert response["Content-Type"] == "application/problem+json"

    def test_renderer_leaves_string_stream_data_unmodified(self):
        renderer = EventStreamRenderer()
        stream_data = "event: connected\ndata: {}\n\n"
        assert renderer.render(stream_data) == stream_data


@pytest.mark.django_db
class TestR22ConcurrentFspLogin:
    @pytest.fixture(autouse=True)
    def demo_idp(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        settings.OIDC_ISSUER = "http://localhost:8000/idp/realms/fsp"
        settings.OIDC_INTERNAL_URL = ""
        idp = APIClient()

        def to_path(url):
            return "/idp/realms/fsp" + url[len("http://localhost:8000/idp/realms/fsp") :]

        def post_form(url, data):
            res = idp.post(to_path(url), data)
            return res.json()

        def get_json(url):
            return idp.get(to_path(url)).json()

        monkeypatch.setattr("identity.oidc._http_post_form", post_form)
        monkeypatch.setattr("identity.oidc._http_get_json", get_json)

    def test_concurrent_first_fsp_login_returns_409_on_integrity_error(self, client):
        # 1. Initiate login flow
        client.get("/api/auth/fsp-id/login?intent=login")
        state = client.session["oidc_state"]
        verifier = client.session["oidc_verifier"]
        redirect_uri = client.session["oidc_redirect_uri"]

        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        code = signing.dumps(
            {
                "client_id": "fsp-draft",
                "redirect_uri": redirect_uri,
                "participant_id": "FSP-RACE-001",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "nonce": client.session["oidc_nonce"],
            },
            salt="fsp-oidc-code",
        )

        # Mock Identity.objects.create to simulate another thread committing first
        with patch.object(
            Identity.objects, "create", side_effect=IntegrityError("duplicate key value")
        ):
            res = client.get(f"/api/auth/fsp-id/callback?code={code}&state={state}")
            assert res.status_code == 409
            data = res.json()
            assert data["code"] == "fsp_id_already_linked"


@pytest.mark.django_db
class TestR22AssessmentMigration0004Reverse:
    def test_backfill_null_deadlines_populates_null_values(self):
        mig = importlib.import_module(
            "assessment.migrations.0004_item_deadline_on_serve_one_active_session"
        )
        backfill_null_deadlines = mig.backfill_null_deadlines
        from assessment.models import AssessmentItem, AssessmentSession, ItemFamily

        user = User.objects.create_user(
            email="test_item@example.com", password="pw", role=UserRole.CANDIDATE
        )
        session = AssessmentSession.objects.create(
            candidate=user,
            specialization="backend",
            claimed_grade="middle",
        )
        family = ItemFamily.objects.create(
            id="test-family",
            specs=["backend"],
            topic="db",
            format="mcq_single",
            a=1.0,
            b=0.0,
        )
        item = AssessmentItem.objects.create(
            assessment=session,
            family=family,
            seq=1,
            seed="seed123",
            view={"stem": "test"},
            key={"answer": "a"},
            deadline_at=None,
        )
        assert item.deadline_at is None

        # Execute the reverse backfill function
        backfill_null_deadlines(apps, None)

        item.refresh_from_db()
        assert item.deadline_at is not None
        assert item.deadline_at == item.served_at
