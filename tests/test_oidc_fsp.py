"""Tests for FSP ID OIDC and Mock IdP / Registry (AI-08 / G15)."""
import base64
import hashlib
import json
import urllib.parse
import pytest
from django.core import signing
from rest_framework.test import APIClient

from core.enums import IdentityProvider, UserRole
from fsp_mock.keys import get_jwks, sign_id_token
from fsp_sync.models import FSPLink
from identity.models import Identity, User
from profiles.models import CandidateProfile, generate_public_id


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email='cand_oidc@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name='Test Candidate OIDC',
    )
    return user


@pytest.fixture
def employer_user(db):
    user = User.objects.create_user(
        email='employer_oidc@example.com',
        password='password123',
        role=UserRole.EMPLOYER,
    )
    return user


@pytest.mark.django_db
class TestMockIdpAndRegistryEndpoints:

    def test_oidc_discovery(self, client):
        res = client.get('/idp/realms/fsp/.well-known/openid-configuration')
        assert res.status_code == 200
        data = res.json()
        assert 'issuer' in data
        assert 'jwks_uri' in data
        assert 'authorization_endpoint' in data
        assert 'token_endpoint' in data
        assert 'userinfo_endpoint' in data
        assert 'RS256' in data['id_token_signing_alg_values_supported']

    def test_oidc_jwks(self, client):
        res = client.get('/idp/realms/fsp/protocol/openid-connect/certs')
        assert res.status_code == 200
        data = res.json()
        assert 'keys' in data
        assert len(data['keys']) >= 1
        key = data['keys'][0]
        assert key['kty'] == 'RSA'
        assert key['alg'] == 'RS256'
        assert key['use'] == 'sig'
        assert 'n' in key and 'e' in key

    def test_oidc_auth_endpoint_consent_and_approve(self, client):
        params = {
            'client_id': 'fsp-draft',
            'redirect_uri': 'http://localhost:8000/api/auth/fsp-id/callback',
            'response_type': 'code',
            'scope': 'openid profile email',
            'state': 'xyz123',
            'code_challenge': 'any_challenge',
            'code_challenge_method': 'S256',
        }
        # GET automatically issues code and redirects in mock IdP
        res = client.get('/idp/realms/fsp/protocol/openid-connect/auth', params)
        assert res.status_code == 302
        redirect_url = res.url
        assert 'http://localhost:8000/api/auth/fsp-id/callback' in redirect_url
        parsed = urllib.parse.urlparse(redirect_url)
        query = urllib.parse.parse_qs(parsed.query)
        assert query['state'][0] == 'xyz123'
        assert 'code' in query

    def test_oidc_token_endpoint_pkce(self, client):
        # Generate code_verifier and code_challenge
        code_verifier = 'test_verifier_string_at_least_43_characters_long_123456789'
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

        code = signing.dumps({
            'client_id': 'fsp-draft',
            'redirect_uri': 'http://localhost:8000/api/auth/fsp-id/callback',
            'participant_id': 'FSP-RU-77-0042',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': 'nonce-test',
        }, salt='fsp-oidc-code')

        # Invalid verifier should fail
        fail_res = client.post('/idp/realms/fsp/protocol/openid-connect/token', {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': 'fsp-draft',
            'client_secret': 'dev-secret',
            'redirect_uri': 'http://localhost:8000/api/auth/fsp-id/callback',
            'code_verifier': 'wrong_verifier',
        })
        assert fail_res.status_code == 400

        # Valid verifier succeeds
        success_res = client.post('/idp/realms/fsp/protocol/openid-connect/token', {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': 'fsp-draft',
            'client_secret': 'dev-secret',
            'redirect_uri': 'http://localhost:8000/api/auth/fsp-id/callback',
            'code_verifier': code_verifier,
        })
        assert success_res.status_code == 200
        token_data = success_res.json()
        assert 'access_token' in token_data
        assert 'id_token' in token_data
        assert token_data['token_type'] == 'Bearer'

    def test_registry_achievements(self, client):
        res = client.get('/registry/v1/participants/FSP-000123/achievements')
        assert res.status_code == 200
        data = res.json()
        assert data['participant_id'] == 'FSP-000123'
        assert 'results' in data
        assert len(data['results']) > 0

        # Non-existent participant returns 404
        res_404 = client.get('/registry/v1/participants/UNKNOWN-999/achievements')
        assert res_404.status_code == 404


@pytest.mark.django_db
class TestFspIdFlows:

    def test_fsp_id_login_initiation(self, client):
        res = client.get('/api/auth/fsp-id/login?intent=login')
        assert res.status_code == 302
        assert '/realms/fsp/protocol/openid-connect/auth' in res.url
        assert client.session.get('oidc_state') is not None
        assert client.session.get('oidc_verifier') is not None
        assert client.session.get('oidc_intent') == 'login'

    def test_fsp_id_login_callback_new_user(self, client):
        # 1. Initiate login to populate session
        login_init = client.get('/api/auth/fsp-id/login?intent=login')
        assert login_init.status_code == 302
        state = client.session['oidc_state']
        verifier = client.session['oidc_verifier']
        redirect_uri = client.session['oidc_redirect_uri']

        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

        code = signing.dumps({
            'client_id': 'fsp-draft',
            'redirect_uri': redirect_uri,
            'participant_id': 'FSP-RU-77-0099',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': client.session['oidc_nonce'],
        }, salt='fsp-oidc-code')

        # 2. Call callback
        callback_res = client.get(f'/api/auth/fsp-id/callback?code={code}&state={state}')
        assert callback_res.status_code == 302
        assert callback_res.url == '/?login=success'

        # Verify user and Identity created
        identity = Identity.objects.get(provider=IdentityProvider.FSP_ID, subject='FSP-RU-77-0099')
        user = identity.user
        assert user.role == UserRole.CANDIDATE
        assert user.candidate_profile is not None
        assert FSPLink.objects.filter(candidate=user, participant_id='FSP-RU-77-0099').exists()

    def test_fsp_id_link_flow_candidate(self, client, candidate_user):
        client.force_login(candidate_user)

        # 1. Initiate link
        init_res = client.get('/api/auth/fsp-id/login?intent=link')
        assert init_res.status_code == 302
        state = client.session['oidc_state']
        verifier = client.session['oidc_verifier']
        redirect_uri = client.session['oidc_redirect_uri']

        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

        code = signing.dumps({
            'client_id': 'fsp-draft',
            'redirect_uri': redirect_uri,
            'participant_id': 'FSP-RU-77-0042',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': client.session['oidc_nonce'],
        }, salt='fsp-oidc-code')

        # 2. Callback
        cb_res = client.get(f'/api/auth/fsp-id/callback?code={code}&state={state}')
        assert cb_res.status_code == 302
        assert cb_res.url == '/candidate/profile?fsp_linked=true'

        assert Identity.objects.filter(
            user=candidate_user,
            provider=IdentityProvider.FSP_ID,
            subject='FSP-RU-77-0042',
        ).exists()
        assert FSPLink.objects.filter(
            candidate=candidate_user,
            participant_id='FSP-RU-77-0042',
        ).exists()

    def test_fsp_id_link_conflict_409(self, client, candidate_user):
        # User 1 has the FSP ID already linked
        Identity.objects.create(
            user=candidate_user,
            provider=IdentityProvider.FSP_ID,
            subject='FSP-RU-77-0042',
        )
        FSPLink.objects.create(
            candidate=candidate_user,
            participant_id='FSP-RU-77-0042',
        )

        # User 2 attempts to link the same FSP ID
        user2 = User.objects.create_user(
            email='user2@example.com',
            password='password123',
            role=UserRole.CANDIDATE,
        )
        CandidateProfile.objects.create(
            user=user2,
            public_id=generate_public_id(),
            full_name='User Two',
        )
        client.force_login(user2)

        init_res = client.get('/api/auth/fsp-id/login?intent=link')
        assert init_res.status_code == 302
        state = client.session['oidc_state']
        verifier = client.session['oidc_verifier']
        redirect_uri = client.session['oidc_redirect_uri']

        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

        code = signing.dumps({
            'client_id': 'fsp-draft',
            'redirect_uri': redirect_uri,
            'participant_id': 'FSP-RU-77-0042',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': client.session['oidc_nonce'],
        }, salt='fsp-oidc-code')

        cb_res = client.get(f'/api/auth/fsp-id/callback?code={code}&state={state}')
        assert cb_res.status_code == 409
        err = cb_res.json()
        assert err['code'] == 'fsp_id_already_linked'

    def test_fsp_id_link_forbidden_for_employer(self, client, employer_user):
        client.force_login(employer_user)
        res = client.get('/api/auth/fsp-id/login?intent=link')
        assert res.status_code == 403
        assert res.json()['code'] == 'forbidden'

    def test_fsp_id_link_unauthenticated_401(self, client):
        res = client.get('/api/auth/fsp-id/login?intent=link')
        assert res.status_code == 401
        assert res.json()['code'] == 'unauthorized'

    def test_fsp_id_callback_state_mismatch_400(self, client):
        client.get('/api/auth/fsp-id/login?intent=login')
        res = client.get('/api/auth/fsp-id/callback?code=somecode&state=forged_state')
        assert res.status_code == 400
        assert res.json()['code'] == 'invalid_state'
