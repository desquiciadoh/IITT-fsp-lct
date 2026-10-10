"""Text embeddings for SemanticFit (ML-9, AI-11). Pure engine module: no Django, no ORM, no core.enums.

Backends, chosen by the EMBEDDINGS environment variable:
  off    (default)  embed_text returns None; SemanticFit stays neutral (0.5) with an info chip.
  local             deepvk/USER-bge-m3 through sentence-transformers on CPU (1024 dims, L2-normalised).
                    If the package or the weights are missing, EmbeddingUnavailable is raised. It is
                    never silently replaced by another backend, because vectors from two backends live
                    in different spaces and their cosine is meaningless. A failed load is remembered,
                    so a missing model costs one attempt per process, not one per text.
  hash              a deterministic feature-hashing projection of word, bigram and character n-grams
                    (1024 dims, L2-normalised). Lexical, not semantic; for tests, offline demos and
                    the validation suite when the model is not installed, and always labelled so.

Every vector is tagged by `active_model_id()`. Store it next to the vector (BE) and pass it in
`CandidateCtx.embedding_model` / `NeedCtx.embedding_model`: SemanticFit refuses to compare vectors
of different models and stays neutral instead. Blank text has no embedding (None), so an empty
profile is neutral rather than penalised.

Latency: vectors are computed at save or seed time, never while scoring; `features.cosine` uses
math.sumprod (about 30 µs per 1024-dim pair), so a 1,500-candidate pool stays well under 300 ms.
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
HASH_MODEL_ID: str = "hash-ngram-1024-v1"
BACKENDS = ("off", "local", "hash")

_TOKEN_RE = re.compile(r"[\w\+\#\.]+", re.UNICODE)
_MODEL_CACHE: dict[str, Any] = {}
_FAILED: dict[str, str] = {}


class EmbeddingUnavailable(RuntimeError):
    """EMBEDDINGS=local but the model cannot be loaded or run."""


def backend() -> str:
    value = os.environ.get("EMBEDDINGS", "off").strip().lower()
    if value not in BACKENDS:
        raise ValueError(f"EMBEDDINGS must be one of {BACKENDS}, got {value!r}")
    return value


def model_name() -> str:
    return os.environ.get("EMBEDDINGS_MODEL", DEFAULT_MODEL)


def active_model_id(kind: str | None = None) -> str | None:
    """The id stored next to vectors of the given (default: active) backend; None when off."""
    kind = kind or backend()
    return {"off": None, "local": model_name(), "hash": HASH_MODEL_ID}[kind]


def candidate_embedding_text(about: str = "", experience_text: str = "", skills: Sequence[str] = (),
                             roles: Sequence[str] = ()) -> str:
    """Candidate profile text for embedding."""
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


def need_embedding_text(title: str = "", description: str = "", must_skills: Sequence[str] = (),
                        nice_skills: Sequence[str] = (), team_context: str = "") -> str:
    """Job text for embedding."""
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


def pseudo_embed(text: str, dim: int = EMBEDDING_DIM) -> tuple[float, ...] | None:
    """Feature hashing of word tokens (weight 1.0), word bigrams (1.5) and character 3/4-grams (0.4)
    into `dim` signed buckets, L2-normalised. Deterministic across processes (sha256, not hash())."""
    clean = text.lower().strip()
    if not clean:
        return None
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(clean)
    features = [(f"w:{t}", 1.0) for t in tokens]
    features += [(f"bi:{tokens[i]}_{tokens[i + 1]}", 1.5) for i in range(len(tokens) - 1)]
    features += [(f"c{k}:{clean[i:i + k]}", 0.4) for k in (3, 4) for i in range(len(clean) - k + 1)]
    for feat, weight in features:
        digest = hashlib.sha256(feat.encode("utf-8")).digest()
        vec[int.from_bytes(digest[:4], "big") % dim] += weight if digest[4] % 2 == 0 else -weight
    norm = math.sqrt(math.sumprod(vec, vec))
    return tuple(x / norm for x in vec) if norm > 1e-12 else None


def _load_model(name: str) -> Any:
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    if name in _FAILED:
        raise EmbeddingUnavailable(_FAILED[name])
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(name, device="cpu")
    except Exception as e:  # missing package, missing weights, no network: remembered, then raised
        _FAILED[name] = f"cannot load embedding model {name!r}: {type(e).__name__}: {e}"
        raise EmbeddingUnavailable(_FAILED[name]) from e
    _MODEL_CACHE[name] = model
    return model


def clear_cache() -> None:
    """Forget loaded models and remembered failures (tests, or after installing the model)."""
    _MODEL_CACHE.clear()
    _FAILED.clear()


def embed_batch(texts: Sequence[str], kind: str | None = None) -> list[tuple[float, ...] | None]:
    """Vectors for `texts` with the given (default: active) backend; None for blank texts and
    for everything when the backend is off. Raises EmbeddingUnavailable for local without a model."""
    kind = kind or backend()
    if kind == "off":
        return [None] * len(texts)
    if kind == "hash":
        return [pseudo_embed(t) for t in texts]
    keep = [i for i, t in enumerate(texts) if t and t.strip()]
    out: list[tuple[float, ...] | None] = [None] * len(texts)
    if keep:
        arr = _load_model(model_name()).encode([texts[i] for i in keep], batch_size=32, normalize_embeddings=True)
        for i, row in zip(keep, arr, strict=True):
            out[i] = tuple(float(x) for x in row)
    return out


def embed_text(text: str, kind: str | None = None) -> tuple[float, ...] | None:
    return embed_batch([text], kind)[0]
