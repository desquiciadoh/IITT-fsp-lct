"""Text embeddings and SemanticFit vector representation (ML-9, AI-11).

Pure engine module: no Django, no ORM, no core.enums.

Model: deepvk/USER-bge-m3 (1024 dimensions, CPU inference).
Configuration:
  EMBEDDINGS=off (default in dev/test): embed_text returns None; SemanticFit uses neutral 0.5.
  EMBEDDINGS=local: embed_text produces 1024-dim L2-normalised vectors. When sentence-transformers
  is available, it uses deepvk/USER-bge-m3; otherwise it falls back to a deterministic, pure-Python
  hashing projection so tests and offline workflows remain fully functional without downloading weights.

Latency constraint:
  Pool scoring p95 stays under 300 ms because candidate and position vectors are pre-computed
  at save/seed time and stored in the DTOs (CandidateCtx.embedding, NeedCtx.embedding).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Sequence
from typing import Any

EMBEDDING_DIM: int = 1024
DEFAULT_MODEL: str = "deepvk/USER-bge-m3"

_TOKEN_RE = re.compile(r"[\w\+\#\.]+", re.UNICODE)
_MODEL_CACHE: dict[str, Any] = {}


def is_embeddings_enabled() -> bool:
    """True if local embedding inference is active (EMBEDDINGS=local)."""
    return os.environ.get("EMBEDDINGS", "off").lower() in ("local", "1", "true")


def get_embedding_model_name() -> str:
    """Name of the HuggingFace / local model to use for embeddings."""
    return os.environ.get("EMBEDDINGS_MODEL", DEFAULT_MODEL)


def candidate_embedding_text(
    about: str = "",
    experience_text: str = "",
    skills: Sequence[str] = (),
    roles: Sequence[str] = (),
) -> str:
    """Format candidate profile text for embedding."""
    parts = []
    if roles:
        parts.append("Роли: " + ", ".join(roles))
    if skills:
        parts.append("Навыки: " + ", ".join(skills))
    if about:
        parts.append("О себе: " + about.strip())
    if experience_text:
        parts.append("Опыт: " + experience_text.strip())
    return "\n".join(p for p in parts if p)


def need_embedding_text(
    title: str = "",
    description: str = "",
    must_skills: Sequence[str] = (),
    nice_skills: Sequence[str] = (),
    team_context: str = "",
) -> str:
    """Format job description and requirements for embedding."""
    parts = []
    if title:
        parts.append("Позиция: " + title.strip())
    if must_skills:
        parts.append("Обязательные навыки: " + ", ".join(must_skills))
    if nice_skills:
        parts.append("Желательные навыки: " + ", ".join(nice_skills))
    if team_context:
        parts.append("Команда и контекст: " + team_context.strip())
    if description:
        parts.append("Описание: " + description.strip())
    return "\n".join(p for p in parts if p)


def pseudo_embed(text: str, dim: int = EMBEDDING_DIM) -> tuple[float, ...]:
    """Deterministic, zero-dependency feature hasher into a unit-length vector of length `dim`.

    Used when sentence-transformers / GPU / internet weights are not available.
    Preserves lexical and n-gram overlap between related texts (cosine > 0.5), while
    orthogonal texts yield near-zero dot products.
    """
    clean = text.lower().strip()
    if not clean:
        return tuple(0.0 for _ in range(dim))

    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(clean)

    features: list[tuple[str, float]] = []
    # 1. Word tokens (weight 1.0)
    for tok in tokens:
        features.append((f"w:{tok}", 1.0))
    # 2. Bigrams (weight 1.5)
    for i in range(len(tokens) - 1):
        features.append((f"bi:{tokens[i]}_{tokens[i+1]}", 1.5))
    # 3. Character 3-grams and 4-grams (weight 0.4)
    for k in (3, 4):
        for i in range(len(clean) - k + 1):
            features.append((f"c{k}:{clean[i:i+k]}", 0.4))

    for feat, weight in features:
        digest = hashlib.sha256(feat.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign * weight

    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:
        return tuple(0.0 for _ in range(dim))
    return tuple(x / norm for x in vec)


def _load_sentence_transformer(model_name: str) -> Any | None:
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name, device="cpu")
        _MODEL_CACHE[model_name] = model
        return model
    except Exception:
        return None


def clear_cache() -> None:
    """Clear cached model instances (for testing)."""
    _MODEL_CACHE.clear()


def embed_text(
    text: str,
    force: bool = False,
    model_name: str | None = None,
) -> tuple[float, ...] | None:
    """Generate an embedding vector for `text`.

    Returns None if embeddings are disabled (EMBEDDINGS=off) and `force` is False.
    Otherwise returns a tuple of 1024 floats with L2 norm = 1.0.
    """
    if not is_embeddings_enabled() and not force:
        return None

    if not text or not text.strip():
        return tuple(0.0 for _ in range(EMBEDDING_DIM))

    name = model_name or get_embedding_model_name()
    model = _load_sentence_transformer(name)
    if model is not None:
        try:
            arr = model.encode(text, normalize_embeddings=True)
            return tuple(float(x) for x in arr)
        except Exception:
            pass

    return pseudo_embed(text, dim=EMBEDDING_DIM)


def embed_batch(
    texts: Sequence[str],
    force: bool = False,
    model_name: str | None = None,
) -> list[tuple[float, ...] | None]:
    """Generate embedding vectors for a batch of texts."""
    if not is_embeddings_enabled() and not force:
        return [None] * len(texts)

    name = model_name or get_embedding_model_name()
    model = _load_sentence_transformer(name)
    if model is not None:
        try:
            arr = model.encode(list(texts), batch_size=32, normalize_embeddings=True)
            return [tuple(float(x) for x in row) for row in arr]
        except Exception:
            pass

    return [embed_text(t, force=True, model_name=name) for t in texts]
