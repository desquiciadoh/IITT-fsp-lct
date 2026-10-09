"""RSA key generator and JWKS provider for FSP Mock IdP."""
from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# A deterministic in-memory RSA key pair generated on module load
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode('utf-8')

_JWK = JsonWebKey.import_key(_PRIVATE_PEM, {'kty': 'RSA'})
_PUBLIC_JWK = _JWK.as_dict(is_crv=False)
_PUBLIC_JWK['use'] = 'sig'
_PUBLIC_JWK['kid'] = 'fsp-mock-key-1'
_PUBLIC_JWK['alg'] = 'RS256'

# JWKS document
JWKS_DOCUMENT = {
    'keys': [_PUBLIC_JWK]
}


def get_jwks() -> dict:
    """Return the JWKS document with the mock public key."""
    return JWKS_DOCUMENT


def sign_id_token(payload: dict) -> str:
    """Sign an OIDC id_token using RS256 and the mock private key."""
    header = {
        'alg': 'RS256',
        'kid': 'fsp-mock-key-1',
        'typ': 'JWT',
    }
    return jwt.encode(header, payload, _PRIVATE_PEM).decode('utf-8')
