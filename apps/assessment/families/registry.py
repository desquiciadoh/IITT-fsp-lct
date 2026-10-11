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


# Retired families (ML-13): still registered, so a session with one pending can finish and old
# instances can be re-graded, but never selected again. A family is retired when its answer is
# guessable from memory: with 20 leaked instances (an answer sheet circulating after a pilot),
# the chance that a new item repeats a leaked question is >= 0.5 (validation `key_reuse`, run on
# 2026-10-10 at commit 992c2a04). They are classification families with few distinct questions.
RETIRED: dict[str, str] = {
    "be.http.status_code.v1": "few distinct questions: P(repeat | 20 leaked) = 0.65",
    "be.http.method.v1": "few distinct questions: P(repeat | 20 leaked) = 1.0",
    "be.sec.vuln_class.v1": "few distinct questions: P(repeat | 20 leaked) = 1.0",
    "be.db.isolation_anomaly.v1": "few distinct questions: P(repeat | 20 leaked) = 1.0",
    "sh.ds.op_cost.v1": "few distinct questions: P(repeat | 20 leaked) = 0.64",
}


def active_metas(spec: str) -> list[FamilyMeta]:
    """Metadata of the active (not retired) families that serve `spec`, in id order. BE syncs these
    into ItemFamily rows; a family missing from the list should be set inactive, not deleted."""
    if spec not in SPECS:
        raise ValueError(f"unknown specialization: {spec!r}")
    return [f.meta for f in all_families().values() if spec in f.meta.specs and f.meta.id not in RETIRED]


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
