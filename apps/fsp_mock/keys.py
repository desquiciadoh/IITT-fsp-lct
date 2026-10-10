"""RSA key and JWKS provider for the FSP Mock IdP (DEMO_MODE only).

The key must be the same in every worker process, otherwise a token signed by
one gunicorn worker fails verification in another. Source, in order:
1. ``FSP_MOCK_PRIVATE_KEY_PEM`` setting/env (PEM, PKCS8).
2. ``<BASE_DIR>/var/fsp_mock_rsa.pem``, created once (temp file + os.link) so
   that concurrent workers converge on the first writer's key.
"""
import os
import threading
from pathlib import Path

from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings

KID = 'fsp-mock-key-1'

_lock = threading.Lock()
_private_pem: str | None = None


def _key_file() -> Path:
    return Path(settings.BASE_DIR) / 'var' / 'fsp_mock_rsa.pem'


def _generate_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')


def _load_or_create_file_pem() -> str:
    """Write a complete key to a temp file, then hard-link it into place.

    os.link fails if the target exists, so concurrent workers never see a
    half-written file and all of them end up reading the first writer's key.
    """
    path = _key_file()
    if path.exists():
        pem = path.read_text(encoding='utf-8')
        if pem.strip():
            return pem
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(_generate_pem(), encoding='utf-8')
    try:
        os.link(tmp, path)
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    pem = path.read_text(encoding='utf-8')
    if not pem.strip():
        raise RuntimeError(f'FSP mock key file is empty: {path}')
    return pem


def _get_private_pem() -> str:
    global _private_pem
    if not _private_pem:
        with _lock:
            if not _private_pem:
                configured = getattr(settings, 'FSP_MOCK_PRIVATE_KEY_PEM', '')
                _private_pem = configured or _load_or_create_file_pem()
    return _private_pem


def get_jwks() -> dict:
    """Return the JWKS document with the mock public key."""
    public_jwk = JsonWebKey.import_key(_get_private_pem(), {'kty': 'RSA'}).as_dict(is_private=False)
    public_jwk.update({'use': 'sig', 'kid': KID, 'alg': 'RS256'})
    return {'keys': [public_jwk]}


def sign_id_token(payload: dict) -> str:
    """Sign an OIDC id_token using RS256 and the mock private key."""
    header = {'alg': 'RS256', 'kid': KID, 'typ': 'JWT'}
    return jwt.encode(header, payload, _get_private_pem()).decode('utf-8')
