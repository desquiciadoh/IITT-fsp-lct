"""Regression tests for the critical fixes after the review of bikhe-p0-backend-fixes.

Each test reproduced a confirmed exploit before the fix.
"""

import base64
import hashlib
import urllib.error

import pytest
from core.enums import IdentityProvider, UserRole
from django.core import signing
from django.utils import timezone
from fsp_sync.models import FSPLink
from identity.models import Identity, User
from matching.models import Company, CompanyMember, Position
from profiles.models import CandidateProfile, generate_public_id
from rest_framework.test import APIClient

ISSUER = "http://localhost:8000/idp/realms/fsp"
MOCK_PATH = "/idp/realms/fsp"


def _candidate(email):
    user = User.objects.create_user(
        email=email,
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(user=user, public_id=generate_public_id(), full_name=email)
    return user


def _victim_with_fsp(participant_id="FSP-000123"):
    victim = _candidate("victim@example.com")
    FSPLink.objects.create(candidate=victim, participant_id=participant_id)
    Identity.objects.create(user=victim, provider=IdentityProvider.FSP_ID, subject=participant_id)
    return victim


def _route_idp(settings, monkeypatch, issuer=ISSUER):
    """Send the OIDC client's server-to-server calls to the in-app mock IdP."""
    settings.OIDC_ISSUER = issuer
    settings.OIDC_INTERNAL_URL = ""
    idp = APIClient()

    def to_path(url):
        return MOCK_PATH + url[len(issuer) :]

    def post_form(url, data):
        res = idp.post(to_path(url), data)
        if res.status_code >= 400:
            raise urllib.error.HTTPError(url, res.status_code, "error", {}, None)
        return res.json()

    def get_json(url):
        res = idp.get(to_path(url))
        if res.status_code >= 400:
            raise urllib.error.URLError("jwks unavailable")
        return res.json()

    monkeypatch.setattr("identity.oidc._http_post_form", post_form)
    monkeypatch.setattr("identity.oidc._http_get_json", get_json)


def _start_login(client):
    res = client.get("/api/auth/fsp-id/login?intent=login")
    assert res.status_code == 302
    return dict(client.session)


def _forge_code(session, participant_id, **overrides):
    """A code exactly as the mock IdP would issue it (same SECRET_KEY)."""
    digest = hashlib.sha256(session["oidc_verifier"].encode("ascii")).digest()
    data = {
        "client_id": "fsp-draft",
        "redirect_uri": session["oidc_redirect_uri"],
        "participant_id": participant_id,
        "code_challenge": base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        "code_challenge_method": "S256",
        "nonce": session["oidc_nonce"],
    }
    data.update(overrides)
    return signing.dumps(data, salt="fsp-oidc-code")


def _callback(client, session, code):
    return client.get(f"/api/auth/fsp-id/callback?code={code}&state={session['oidc_state']}")


@pytest.mark.django_db
class TestFspIdTakeover:
    def test_mock_idp_and_registry_are_404_outside_demo(self, settings):
        settings.DEMO_MODE = False
        client = APIClient()
        assert client.get(f"{MOCK_PATH}/.well-known/openid-configuration").status_code == 404
        assert (
            client.get(
                f"{MOCK_PATH}/protocol/openid-connect/auth",
                {
                    "client_id": "fsp-draft",
                    "redirect_uri": "http://x/api/auth/fsp-id/callback",
                    "participant_id": "FSP-000123",
                    "code_challenge": "c",
                    "code_challenge_method": "S256",
                },
            ).status_code
            == 404
        )
        assert client.post(f"{MOCK_PATH}/protocol/openid-connect/token", {}).status_code == 404
        assert client.get("/registry/v1/participants/FSP-000123/achievements").status_code == 404

    def test_forged_code_does_not_log_in_outside_demo(self, settings, monkeypatch):
        """Before the fix a failed token exchange fell back to minting a token locally."""
        _victim_with_fsp()
        settings.DEMO_MODE = False
        _route_idp(settings, monkeypatch)  # the mock IdP answers 404 outside demo
        client = APIClient()
        session = _start_login(client)
        res = _callback(client, session, _forge_code(session, "FSP-000123"))
        assert res.status_code == 400
        assert res.json()["code"] == "token_exchange_failed"
        assert client.get("/api/me").status_code in (401, 403)

    def test_unreachable_idp_is_502_not_a_login(self, settings, monkeypatch):
        _victim_with_fsp()
        settings.OIDC_ISSUER = ISSUER

        def unreachable(url, data):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("identity.oidc._http_post_form", unreachable)
        client = APIClient()
        session = _start_login(client)
        res = _callback(client, session, _forge_code(session, "FSP-000123"))
        assert res.status_code == 502
        assert res.json()["code"] == "fsp_id_unavailable"
        assert "connection refused" not in res.content.decode()
        assert client.get("/api/me").status_code in (401, 403)

    def test_wrong_pkce_challenge_is_rejected(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        client = APIClient()
        session = _start_login(client)
        res = _callback(
            client, session, _forge_code(session, "FSP-000123", code_challenge="not-it")
        )
        assert res.status_code == 400
        assert res.json()["code"] == "token_exchange_failed"

    def test_wrong_nonce_is_rejected(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        client = APIClient()
        session = _start_login(client)
        res = _callback(
            client, session, _forge_code(session, "FSP-RU-77-0001", nonce="other-nonce")
        )
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_token"
        assert not Identity.objects.filter(subject="FSP-RU-77-0001").exists()

    def test_wrong_audience_is_rejected(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        client = APIClient()
        session = _start_login(client)
        res = _callback(
            client, session, _forge_code(session, "FSP-RU-77-0001", client_id="another-client")
        )
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_token"

    def test_wrong_issuer_is_rejected(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        client = APIClient()
        session = _start_login(client)
        code = _forge_code(session, "FSP-RU-77-0001")
        idp = APIClient()
        token = idp.post(
            f"{MOCK_PATH}/protocol/openid-connect/token",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": session["oidc_redirect_uri"],
                "code_verifier": session["oidc_verifier"],
            },
        ).json()
        settings.OIDC_ISSUER = "https://other-issuer.example"
        monkeypatch.setattr("identity.oidc._http_post_form", lambda url, data: token)
        monkeypatch.setattr(
            "identity.oidc._http_get_json",
            lambda url: idp.get(f"{MOCK_PATH}/protocol/openid-connect/certs").json(),
        )
        res = _callback(client, session, code)
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_token"

    def test_state_is_single_use(self, settings, monkeypatch):
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        client = APIClient()
        session = _start_login(client)
        code = _forge_code(session, "FSP-RU-77-0002")
        assert _callback(client, session, code).status_code == 302
        res = _callback(client, session, code)
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_state"

    def test_existing_email_account_is_not_hijacked(self, settings, monkeypatch):
        """The FSP login used to attach the identity to any account with the token's email."""
        settings.DEMO_MODE = True
        _route_idp(settings, monkeypatch)
        User.objects.create_user(
            email="fsp000777@fsp-sports.ru", password="x", role=UserRole.EMPLOYER
        )
        client = APIClient()
        session = _start_login(client)
        res = _callback(client, session, _forge_code(session, "FSP-000777"))
        assert res.status_code == 409
        assert res.json()["code"] == "account_exists"
        assert not Identity.objects.filter(subject="FSP-000777").exists()

    def test_mock_idp_rejects_foreign_redirect_uri(self, settings):
        settings.DEMO_MODE = True
        res = APIClient().get(
            f"{MOCK_PATH}/protocol/openid-connect/auth",
            {
                "client_id": "fsp-draft",
                "redirect_uri": "https://evil.example/steal",
                "code_challenge": "c",
                "code_challenge_method": "S256",
            },
        )
        assert res.status_code == 400


@pytest.mark.django_db
class TestBareFspLink:
    def test_bare_link_is_forbidden_outside_demo(self, settings):
        settings.DEMO_MODE = False
        user = _candidate("claimer@example.com")
        client = APIClient()
        client.force_authenticate(user)
        res = client.post("/api/fsp/link", {"participant_id": "FSP-000123"}, format="json")
        assert res.status_code == 403
        assert res.json()["code"] == "fsp_oidc_required"
        assert not FSPLink.objects.filter(candidate=user).exists()

    def test_bare_link_still_works_in_demo(self, settings):
        settings.DEMO_MODE = True
        user = _candidate("demo@example.com")
        client = APIClient()
        client.force_authenticate(user)
        res = client.post("/api/fsp/link", {"participant_id": "FSP-000123"}, format="json")
        assert res.status_code == 200


def _employer_with_two_companies():
    own = Company.objects.create(name="Own", contact_email="a@a.ru")
    other = Company.objects.create(name="Other", contact_email="b@b.ru")
    employer = User.objects.create_user(email="hr@a.ru", password="p", role=UserRole.EMPLOYER)
    CompanyMember.objects.create(company=own, user=employer)
    client = APIClient()
    client.force_authenticate(employer)
    return client, own, other


@pytest.mark.django_db
def test_position_cannot_be_moved_to_another_company():
    client, own, other = _employer_with_two_companies()
    position = Position.objects.create(
        company=own,
        title="Dev",
        specialization="backend",
        grades=["middle"],
        salary_min=100,
        salary_max=200,
        salary_type="gross",
        must_skills=["python"],
    )
    client.put(f"/api/positions/{position.id}", {"company": str(other.id)}, format="json")
    position.refresh_from_db()
    assert position.company_id == own.id


@pytest.mark.django_db
def test_position_create_ignores_company_in_body():
    client, own, other = _employer_with_two_companies()
    res = client.post(
        "/api/positions",
        {
            "company": str(other.id),
            "title": "Dev",
            "specialization": "backend",
            "grades": ["middle"],
            "salary_min": 100,
            "salary_max": 200,
            "salary_type": "gross",
            "must_skills": ["python"],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    assert Position.objects.get(id=res.json()["id"]).company_id == own.id


@pytest.mark.django_db
def test_csrf_cookie_is_readable_by_the_spa():
    res = APIClient().get("/api/auth/csrf")
    cookie = res.cookies.get("csrftoken")
    assert cookie is not None
    assert not cookie["httponly"]


def test_mock_signing_key_is_shared_via_file(settings, tmp_path):
    """Every worker process must sign with the same key."""
    import fsp_mock.keys as keys

    settings.BASE_DIR = tmp_path
    settings.FSP_MOCK_PRIVATE_KEY_PEM = ""
    keys._private_pem = None
    try:
        first = keys.get_jwks()
        keys._private_pem = None  # simulate another process
        assert keys.get_jwks() == first
        assert (tmp_path / "var" / "fsp_mock_rsa.pem").exists()
    finally:
        keys._private_pem = None
