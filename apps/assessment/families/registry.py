"""Family registry and the HMAC seed (ML.md §3).

Families live one per module under shared/, backend/, frontend/ and ml_data/; each
subpackage exports `FAMILIES`, a list of family instances.
"""
from __future__ import annotations

import hashlib
import hmac
import random

from .base import SPECS, FamilyMeta, ItemFamily


def all_families() -> dict[str, ItemFamily]:
    """Every registered family by id, in id order."""
    from . import backend, frontend, ml_data, shared

    found: dict[str, ItemFamily] = {}
    for pkg in (shared, backend, frontend, ml_data):
        for fam in pkg.FAMILIES:
            fid = fam.meta.id
            if fid in found:
                raise ValueError(f"duplicate family id: {fid}")
            found[fid] = fam
    return {fid: found[fid] for fid in sorted(found)}


def active_metas(spec: str) -> list[FamilyMeta]:
    """Metadata of the families that serve `spec`, in id order. BE syncs these into ItemFamily rows."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    return [f.meta for f in all_families().values() if spec in f.meta.specs]


def make_rng(secret: bytes, session_id: str, purpose: str, n: int) -> random.Random:
    """HMAC-SHA256(secret, f"{session_id}|{purpose}|{n}") -> seeded random.Random.

    purpose = family_id for item generation (n = the item's seq, so re-serving a pending item
    renders the same instance), "select" for randomesque selection (n = the selection step).
    The whole 256-bit digest seeds the generator, so seeds can't be guessed without the secret.
    A str secret (Django settings) is UTF-8 encoded; an empty secret is refused.
    """
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not secret:
        raise ValueError("make_rng needs a non-empty secret (settings.ITEM_SEED_SECRET)")
    msg = f"{session_id}|{purpose}|{n}".encode()
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    return random.Random(int.from_bytes(digest, "big"))
