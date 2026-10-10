"""OIDC Client integration for FSP ID (AI-08 / G15)."""

import base64
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from core.errors import FSPAPIError
from django.conf import settings
from django.urls import reverse
from joserfc import jwk, jwt
from joserfc.jwt import JWTClaimsRegistry

logger = logging.getLogger(__name__)


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE (code_verifier, code_challenge) with S256 method."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def get_oidc_endpoints() -> dict:
    """Retrieve OIDC endpoints from settings."""
    issuer = getattr(settings, "OIDC_ISSUER", "http://localhost:8000/idp/realms/fsp").rstrip("/")
    internal_url = (getattr(settings, "OIDC_INTERNAL_URL", "") or issuer).rstrip("/")
    client_id = getattr(settings, "OIDC_CLIENT_ID", "fsp-draft")
    client_secret = getattr(settings, "OIDC_CLIENT_SECRET", "dev-secret")

    return {
        "issuer": issuer,
        "internal_url": internal_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{internal_url}/protocol/openid-connect/token",
        "userinfo_endpoint": f"{internal_url}/protocol/openid-connect/userinfo",
        "jwks_uri": f"{internal_url}/protocol/openid-connect/certs",
    }


def build_authorization_url(request, intent: str) -> tuple[str, str]:
    """Build the authorization URL and persist state in the session."""
    endpoints = get_oidc_endpoints()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce_pair()

    redirect_uri = request.build_absolute_uri(reverse("fsp-id-callback"))

    # Save OIDC session state
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    request.session["oidc_verifier"] = code_verifier
    request.session["oidc_intent"] = intent
    request.session["oidc_redirect_uri"] = redirect_uri
    request.session.modified = True

    params = {
        "client_id": endpoints["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query_string = urllib.parse.urlencode(params)
    auth_url = f"{endpoints['authorization_endpoint']}?{query_string}"
    return auth_url, state


def _http_post_form(url: str, data: dict) -> dict:
    """POST a form to the IdP and return the JSON body (tests patch this)."""
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_json(url: str) -> dict:
    """GET a JSON document from the IdP (tests patch this)."""
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def exchange_code_for_tokens(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """Exchange the authorization code at the IdP token endpoint.

    There is deliberately no local fallback: minting tokens in-process would
    skip PKCE and let a forged code log in as anyone.
    """
    endpoints = get_oidc_endpoints()
    try:
        return _http_post_form(
            endpoints["token_endpoint"],
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": endpoints["client_id"],
                "client_secret": endpoints["client_secret"],
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
    except urllib.error.HTTPError as exc:
        logger.warning("OIDC token endpoint rejected the code: HTTP %s", exc.code)
        raise FSPAPIError(
            "token_exchange_failed",
            "Token exchange failed",
            "The identity provider rejected the code",
            400,
        ) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.error("OIDC token endpoint unavailable", exc_info=True)
        raise FSPAPIError(
            "fsp_id_unavailable",
            "FSP ID unavailable",
            "The identity provider is unavailable",
            502,
        ) from exc


def _get_jwks() -> dict:
    endpoints = get_oidc_endpoints()
    try:
        return _http_get_json(endpoints["jwks_uri"])
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.error("OIDC JWKS unavailable", exc_info=True)
        raise FSPAPIError(
            "fsp_id_unavailable",
            "FSP ID unavailable",
            "The identity provider is unavailable",
            502,
        ) from exc


def verify_and_decode_id_token(id_token: str, nonce: str | None = None) -> dict:
    """Verify the RS256 signature (IdP JWKS) and the iss, aud, exp and nonce claims."""
    endpoints = get_oidc_endpoints()
    if not nonce:
        raise FSPAPIError("invalid_token", "Invalid ID Token", "Missing nonce in session", 400)
    try:
        key_set = jwk.KeySet.import_key_set(_get_jwks())
        token = jwt.decode(id_token, key_set, algorithms=["RS256"])
        claims_registry = JWTClaimsRegistry(
            iss={"essential": True, "value": endpoints["issuer"]},
            aud={"essential": True, "value": endpoints["client_id"]},
            exp={"essential": True},
            nonce={"essential": True, "value": nonce},
            leeway=30,
        )
        claims_registry.validate(token.claims)
        # Explicit check: don't rely on authlib/joserfc validating custom claims
        if not secrets.compare_digest(str(token.claims.get("nonce", "")), nonce):
            raise ValueError("nonce mismatch")
    except FSPAPIError:
        raise
    except Exception as exc:  # joserfc raises several unrelated error types
        logger.warning("Rejected FSP ID token: %s", type(exc).__name__)
        raise FSPAPIError(
            "invalid_token",
            "Invalid ID Token",
            "Failed to verify ID token",
            400,
        ) from exc
    return dict(token.claims)
