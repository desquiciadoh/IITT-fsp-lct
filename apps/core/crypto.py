"""Cryptographic utilities and field encryption for data protection at rest."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """Return a 32-byte URL-safe base64-encoded Fernet key.

    Uses settings.CONTACTS_ENCRYPTION_KEY if provided, otherwise deterministically
    derives a Fernet key from settings.SECRET_KEY via SHA-256.
    """
    custom_key = getattr(settings, "CONTACTS_ENCRYPTION_KEY", None)
    if custom_key:
        if isinstance(custom_key, str):
            custom_key = custom_key.encode("utf-8")
        if len(custom_key) == 44 and custom_key.endswith(b"="):
            return custom_key
        return base64.urlsafe_b64encode(hashlib.sha256(custom_key).digest())

    secret = getattr(settings, "SECRET_KEY", "fsp-draft-default-insecure-secret").encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(secret).digest())


def encrypt_text(plaintext: str | None) -> str | None:
    """Encrypt a plaintext string using Fernet.

    Returns the ciphertext token as a string. If the input is None or empty,
    it returns it as-is. If it already appears to be an encrypted Fernet token,
    it returns it without double-encrypting.
    """
    if plaintext is None or plaintext == "":
        return plaintext
    val_str = str(plaintext)
    if val_str.startswith("gAAAAA") and len(val_str) > 60:
        return val_str
    try:
        fernet = Fernet(get_encryption_key())
        return fernet.encrypt(val_str.encode("utf-8")).decode("utf-8")
    except Exception:
        logger.exception("Failed to encrypt text")
        return val_str


def decrypt_text(ciphertext: str | None) -> str | None:
    """Decrypt a Fernet ciphertext string.

    Returns the decrypted plaintext. If the input is None, empty, or not a Fernet
    token, returns the string as-is.
    """
    if ciphertext is None or ciphertext == "":
        return ciphertext
    val_str = str(ciphertext)
    if not (val_str.startswith("gAAAAA") and len(val_str) > 60):
        # Plaintext value
        return val_str
    try:
        fernet = Fernet(get_encryption_key())
        return fernet.decrypt(val_str.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        logger.warning("Decryption failed or invalid token, returning raw value")
        return val_str


class EncryptedCharField(models.CharField):
    """CharField that transparently encrypts data at rest in the database."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 512)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("max_length") == 512:
            del kwargs["max_length"]
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_text(value)

    def to_python(self, value):
        if isinstance(value, str):
            return decrypt_text(value)
        return value

    def get_prep_value(self, value):
        val = super().get_prep_value(value)
        if val is None or val == "":
            return val
        return encrypt_text(str(val))
