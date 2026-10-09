"""Mock FSP OIDC Identity Provider and Registry views."""
import base64
import hashlib
import time
import uuid

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from django.views import View

from fsp_mock.keys import get_jwks, sign_id_token
from fsp_sync.registry import MOCK_REGISTRY, get_registry_data


def _get_issuer() -> str:
    return getattr(settings, 'OIDC_ISSUER', 'http://localhost:8000/idp/realms/fsp').rstrip('/')


def _get_internal_url() -> str:
    return getattr(settings, 'OIDC_INTERNAL_URL', _get_issuer()).rstrip('/')


class OidcDiscoveryView(View):
    """OIDC Discovery endpoint (/.well-known/openid-configuration)."""

    def get(self, request, *args, **kwargs):
        issuer = _get_issuer()
        internal_url = _get_internal_url()

        config = {
            'issuer': issuer,
            'authorization_endpoint': f'{issuer}/protocol/openid-connect/auth',
            'token_endpoint': f'{internal_url}/protocol/openid-connect/token',
            'userinfo_endpoint': f'{internal_url}/protocol/openid-connect/userinfo',
            'jwks_uri': f'{internal_url}/protocol/openid-connect/certs',
            'response_types_supported': ['code'],
            'subject_types_supported': ['public'],
            'id_token_signing_alg_values_supported': ['RS256'],
            'scopes_supported': ['openid', 'profile', 'email'],
            'token_endpoint_auth_methods_supported': ['client_secret_post', 'client_secret_basic', 'none'],
            'code_challenge_methods_supported': ['S256'],
        }
        return JsonResponse(config)


class OidcJwksView(View):
    """JWKS endpoint returning the RSA public key."""

    def get(self, request, *args, **kwargs):
        return JsonResponse(get_jwks())


class OidcAuthorizeView(View):
    """OIDC authorization endpoint.

    In demo / tests, automatically or manually picks a synthetic participant
    and redirects back to the caller's redirect_uri with an authorization code.
    """

    def get(self, request, *args, **kwargs):
        client_id = request.GET.get('client_id')
        redirect_uri = request.GET.get('redirect_uri')
        response_type = request.GET.get('response_type', 'code')
        state = request.GET.get('state', '')
        nonce = request.GET.get('nonce', '')
        code_challenge = request.GET.get('code_challenge', '')
        code_challenge_method = request.GET.get('code_challenge_method', 'S256')

        if not redirect_uri:
            return HttpResponseBadRequest('Missing redirect_uri')

        participant_id = request.GET.get('participant_id')
        if not participant_id:
            # Pick the first available synthetic participant by default
            participant_id = list(MOCK_REGISTRY.keys())[0] if MOCK_REGISTRY else 'FSP-000123'

        # Generate a signed authorization code (expires in 5 minutes)
        code_data = {
            'participant_id': participant_id,
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'nonce': nonce,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'ts': time.time(),
        }
        code = signing.dumps(code_data, salt='fsp-oidc-code')

        separator = '&' if '?' in redirect_uri else '?'
        redirect_target = f'{redirect_uri}{separator}code={code}'
        if state:
            redirect_target += f'&state={state}'

        return HttpResponseRedirect(redirect_target)


class OidcTokenView(View):
    """OIDC Token endpoint exchanging code for RS256 id_token and access_token."""

    def post(self, request, *args, **kwargs):
        grant_type = request.POST.get('grant_type')
        code = request.POST.get('code')
        code_verifier = request.POST.get('code_verifier')

        if grant_type != 'authorization_code':
            return JsonResponse({'error': 'unsupported_grant_type'}, status=400)
        if not code:
            return JsonResponse({'error': 'invalid_request', 'error_description': 'Missing code'}, status=400)

        try:
            code_data = signing.loads(code, salt='fsp-oidc-code', max_age=300)
        except (signing.BadSignature, signing.SignatureExpired):
            return JsonResponse({'error': 'invalid_grant', 'error_description': 'Code expired or invalid'}, status=400)

        # PKCE validation if code_challenge was provided
        expected_challenge = code_data.get('code_challenge')
        if expected_challenge:
            if not code_verifier:
                return JsonResponse({'error': 'invalid_request', 'error_description': 'Missing code_verifier'}, status=400)
            digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
            computed_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
            if computed_challenge != expected_challenge:
                return JsonResponse({'error': 'invalid_grant', 'error_description': 'PKCE verification failed'}, status=400)

        participant_id = code_data['participant_id']
        issuer = _get_issuer()
        client_id = code_data.get('client_id') or getattr(settings, 'OIDC_CLIENT_ID', 'fsp-draft')

        now = int(time.time())
        id_token_payload = {
            'iss': issuer,
            'sub': participant_id,
            'aud': client_id,
            'fsp_participant_id': participant_id,
            'name': f'Participant {participant_id}',
            'email': f'{participant_id.lower().replace("-", "")}@fsp-sports.ru',
            'iat': now,
            'exp': now + 3600,
        }
        if code_data.get('nonce'):
            id_token_payload['nonce'] = code_data['nonce']

        id_token = sign_id_token(id_token_payload)
        access_token = f'fsp_at_{participant_id}_{uuid.uuid4().hex}'

        return JsonResponse({
            'access_token': access_token,
            'id_token': id_token,
            'token_type': 'Bearer',
            'expires_in': 3600,
        })


class OidcUserinfoView(View):
    """OIDC userinfo endpoint."""

    def get(self, request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        participant_id = None
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            if token.startswith('fsp_at_'):
                parts = token.split('_')
                if len(parts) >= 3:
                    participant_id = parts[2]

        if not participant_id:
            participant_id = request.GET.get('participant_id', 'FSP-000123')

        return JsonResponse({
            'sub': participant_id,
            'fsp_participant_id': participant_id,
            'name': f'Participant {participant_id}',
            'email': f'{participant_id.lower().replace("-", "")}@fsp-sports.ru',
        })


class RegistryAchievementsView(View):
    """FSP Registry achievements endpoint: /registry/v1/participants/<id>/achievements."""

    def get(self, request, participant_id: str, *args, **kwargs):
        data = get_registry_data(participant_id)
        if not data:
            return JsonResponse({'error': 'not_found', 'detail': f'Participant {participant_id} not found'}, status=404)

        return JsonResponse({
            'participant_id': participant_id,
            'sports_rank': data.get('sports_rank', ''),
            'results': data.get('results', []),
        })
