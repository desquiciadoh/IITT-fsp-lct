"""ML-9: embedding backends and SemanticFit. Hermetic: the model loader is stubbed, nothing is downloaded."""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import statistics
import time

import pytest
from matching.engine import embeddings as E
from matching.engine import features as F
from matching.engine.score import score_pool
from matching.engine.types import CandidateCtx, NeedCtx, SkillEvidence, Weights

NOW = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch):
    """No test may load sentence-transformers or reach the network."""
    E.clear_cache()

    def refuse(name, device=None):
        raise ImportError("sentence_transformers is stubbed out in tests")
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers",
                        type("Stub", (), {"SentenceTransformer": staticmethod(refuse)}))
    yield
    E.clear_cache()


def _need(emb=None, model=None) -> NeedCtx:
    return NeedCtx(position_id="P-1", specialization="backend", grades=("middle",), allow_adjacent=False,
                   must_skills=("python",), nice_skills=(), work_formats=("remote",), location="Москва",
                   salary_min=150_000, salary_max=250_000, salary_type="gross", embedding=emb, embedding_model=model)


def _cand(pid: str, emb=None, model=None) -> CandidateCtx:
    return CandidateCtx(public_id=pid, specialization="backend", league_grade="middle", league_status="confirmed",
                        theta=0.5, se=0.2, rating=1100, percentile=70.0, strength=75.0,
                        skills=(SkillEvidence("python", "test", 1.0),), topic_levels={}, fsp_rank=None,
                        fsp_results=(), salary_min=180_000, salary_max=220_000, salary_type="gross",
                        work_formats=("remote",), city="Москва", timezone="UTC+3", last_active_at=NOW,
                        embedding=emb, embedding_model=model)


# ── backends ───────────────────────────────────────────────────────────────

def test_off_is_the_default_and_returns_none(monkeypatch):
    monkeypatch.delenv("EMBEDDINGS", raising=False)
    assert E.backend() == "off" and E.active_model_id() is None
    assert E.embed_text("Python backend") is None and E.embed_batch(["a", "b"]) == [None, None]


def test_local_without_the_model_raises_once_and_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    calls = []
    monkeypatch.setattr(E, "_FAILED", {})

    def loader(name, device=None):
        calls.append(name)
        raise ImportError("no package")
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers",
                        type("Stub", (), {"SentenceTransformer": staticmethod(loader)}))
    with pytest.raises(E.EmbeddingUnavailable):
        E.embed_text("Python backend")
    with pytest.raises(E.EmbeddingUnavailable):
        E.embed_batch(["one", "two", "three"])
    assert calls == ["deepvk/USER-bge-m3"]                 # the failure is remembered
    assert E.active_model_id() == "deepvk/USER-bge-m3"


def test_local_with_a_model_encodes_and_keeps_blank_texts_none(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")

    class Fake:
        def __init__(self, name, device):
            assert device == "cpu"

        def encode(self, texts, batch_size, normalize_embeddings):
            assert normalize_embeddings
            return [[1.0, 0.0] if "python" in t.lower() else [0.0, 1.0] for t in texts]
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers",
                        type("Stub", (), {"SentenceTransformer": Fake}))
    assert E.embed_batch(["Python dev", "  ", "Vue dev"]) == [(1.0, 0.0), None, (0.0, 1.0)]


def test_unknown_backend_is_refused(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "true")
    with pytest.raises(ValueError):
        E.backend()


def test_hash_backend_is_deterministic_normalised_and_pinned(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "hash")
    assert E.active_model_id() == E.HASH_MODEL_ID
    v = E.embed_text("Senior Python backend developer: Django, PostgreSQL")
    assert len(v) == 1024 and math.sqrt(sum(x * x for x in v)) == pytest.approx(1.0, abs=1e-9)
    # a silent change to stored vectors must fail here
    digest = hashlib.sha256(json.dumps([round(x, 9) for x in v]).encode()).hexdigest()
    assert digest == "69f48f83c0e32059c6c7f1f5e0f39d67fea3efaa834e853690d67f45f0ba4d71"
    assert E.embed_text("   ") is None


def test_hash_similarity_is_lexical(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "hash")
    need = E.embed_text("Python backend developer, Django, PostgreSQL, REST API")
    near = E.embed_text("Backend developer: Python, Django, PostgreSQL")
    far = E.embed_text("Frontend: Vue.js, HTML, CSS, Webpack")
    assert F.cosine(need, near) > F.cosine(need, far) + 0.2


def test_text_helpers():
    c = E.candidate_embedding_text(about="Люблю нагрузку", experience_text="3 года в финтехе",
                                   skills=["Python", "Kafka"], roles=["Backend Developer"])
    assert c.splitlines() == ["Роли: Backend Developer", "Навыки: Python, Kafka", "О себе: Люблю нагрузку",
                              "Опыт: 3 года в финтехе"]
    n = E.need_embedding_text(title="Backend", description="Платежи", must_skills=["Python"], nice_skills=["Go"])
    assert n.splitlines() == ["Позиция: Backend", "Обязательные навыки: Python", "Желательные навыки: Go",
                              "Описание: Платежи"]


# ── SemanticFit ────────────────────────────────────────────────────────────

def test_cosine_by_hand():
    assert F.cosine((3.0, 4.0), (4.0, 3.0)) == pytest.approx(24 / 25)
    assert F.cosine((0.0, 0.0), (1.0, 0.0)) == 0.0
    with pytest.raises(ValueError):
        F.cosine((1.0,), (1.0, 0.0))


def test_semantic_fit_maps_cosine_and_refuses_mixed_models():
    need = _need((1.0, 0.0), "m1")
    # cos 0.5 -> (0.5 − 0.2) / 0.6 = 0.5
    value, reasons = F.semantic_fit(need, _cand("c", (0.5, math.sqrt(0.75)), "m1"))
    assert value == pytest.approx(0.5) and reasons[0].kind == "info"
    assert F.semantic_fit(need, _cand("c", (1.0, 0.0), "m1"))[0] == 1.0
    mixed, chips = F.semantic_fit(need, _cand("c", (1.0, 0.0), "m2"))
    assert mixed == 0.5 and chips[0].text == "Смысловое сходство не рассчитано"
    assert F.semantic_fit(need, _cand("c", None))[0] == 0.5


def test_pool_of_1500_with_1024_dim_vectors_scores_within_budget(monkeypatch):
    """The scoring part of the pool p95 < 300 ms budget (ARCHITECTURE §5.3), at full league size."""
    monkeypatch.setenv("EMBEDDINGS", "hash")
    need = _need(E.embed_text("Python backend developer, PostgreSQL"), E.HASH_MODEL_ID)
    pool = [_cand(f"c{i}", E.embed_text(f"Кандидат {i}: Python, SQL, опыт {i % 7} лет"), E.HASH_MODEL_ID)
            for i in range(1500)]
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        score_pool(need, pool, Weights(), NOW)
        times.append((time.perf_counter() - t0) * 1000)
    assert statistics.median(times) < 250, times
