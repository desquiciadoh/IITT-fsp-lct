"""Tests for ML-9 (Embeddings & SemanticFit).

Pure tests: no DB, no network, runs under pytest tests/ml.
"""
from __future__ import annotations

import math
import time

import pytest
from matching.engine import embeddings as E
from matching.engine import features as F
from matching.engine.types import CandidateCtx, NeedCtx


def test_embeddings_disabled_by_default(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "off")
    assert not E.is_embeddings_enabled()
    assert E.embed_text("Python backend developer") is None


def test_embeddings_enabled_returns_1024_dim_normalized_vector(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    assert E.is_embeddings_enabled()

    vec = E.embed_text("Senior Python backend developer with Django and PostgreSQL")
    assert vec is not None
    assert len(vec) == 1024
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm == pytest.approx(1.0, abs=1e-5)
    assert all(math.isfinite(x) for x in vec)


def test_embeddings_empty_text(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    vec = E.embed_text("")
    assert vec is not None
    assert len(vec) == 1024
    assert all(x == 0.0 for x in vec)


def test_embeddings_deterministic(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    text = "Machine Learning engineer, PyTorch, Transformers, NLP"
    vec1 = E.embed_text(text)
    vec2 = E.embed_text(text)
    assert vec1 == vec2


def test_text_formatting_helpers():
    c_text = E.candidate_embedding_text(
        about="Люблю высоконагруженные системы",
        experience_text="3 года в финтехе, проектировал биллинг",
        skills=["Python", "PostgreSQL", "Kafka"],
        roles=["Backend Developer"],
    )
    assert "Backend Developer" in c_text
    assert "PostgreSQL" in c_text
    assert "биллинг" in c_text

    n_text = E.need_embedding_text(
        title="Senior Python Engineer",
        description="Разработка сервисов авторизации и платежей",
        must_skills=["Python", "FastAPI"],
        nice_skills=["Docker", "Redis"],
        team_context="Команда из 5 инженеров",
    )
    assert "Senior Python Engineer" in n_text
    assert "FastAPI" in n_text
    assert "платежей" in n_text


def test_semantic_similarity_overlap(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    need_t = E.need_embedding_text(
        title="Python Backend Developer",
        description="Разработка микросервисов на Python и PostgreSQL",
        must_skills=["Python", "PostgreSQL"],
    )
    cand_match_t = E.candidate_embedding_text(
        experience_text="Разработка бэкенда на Python, работа с базой данных PostgreSQL",
        skills=["Python", "PostgreSQL"],
    )
    cand_unrel_t = E.candidate_embedding_text(
        experience_text="Дизайн интерфейсов в Figma, верстка макетов для полиграфии",
        skills=["Figma", "Photoshop"],
    )

    v_need = E.embed_text(need_t)
    v_match = E.embed_text(cand_match_t)
    v_unrel = E.embed_text(cand_unrel_t)

    assert v_need is not None and v_match is not None and v_unrel is not None
    cos_match = F.cosine(v_need, v_match)
    cos_unrel = F.cosine(v_need, v_unrel)

    assert cos_match > cos_unrel
    assert cos_match > 0.45
    assert cos_unrel < 0.25


def test_semantic_fit_integration(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    v_need = E.embed_text("Backend Python developer with database experience")
    v_cand_high = E.embed_text("Experienced Backend Python developer, relational databases")
    v_cand_low = E.embed_text("Frontend Vue.js developer, HTML CSS Webpack")

    need = NeedCtx(
        position_id="P-1",
        specialization="backend",
        grades=("middle",),
        allow_adjacent=False,
        must_skills=("python",),
        nice_skills=(),
        work_formats=("remote",),
        location="Москва",
        salary_min=150_000,
        salary_max=250_000,
        salary_type="gross",
        embedding=v_need,
    )

    def _cand(pid: str, emb):
        return CandidateCtx(
            public_id=pid,
            specialization="backend",
            league_grade="middle",
            league_status="confirmed",
            theta=0.5,
            se=0.2,
            rating=1100,
            percentile=70.0,
            strength=75.0,
            skills=(),
            topic_levels={},
            fsp_rank=None,
            fsp_results=(),
            salary_min=180_000,
            salary_max=220_000,
            salary_type="gross",
            work_formats=("remote",),
            city="Москва",
            timezone="UTC+3",
            last_active_at=None,
            embedding=emb,
        )

    # 1. Matching candidate
    fit_high, reasons_high = F.semantic_fit(need, _cand("C-1", v_cand_high))
    assert fit_high > 0.5
    assert any("смысловое сходство" in r.text for r in reasons_high)

    # 2. Unrelated candidate
    fit_low, reasons_low = F.semantic_fit(need, _cand("C-2", v_cand_low))
    assert fit_low < fit_high

    # 3. Missing embedding candidate -> neutral 0.5
    fit_none, reasons_none = F.semantic_fit(need, _cand("C-3", None))
    assert fit_none == 0.5
    assert reasons_none[0].text == "Смысловое сходство не рассчитано"


def test_embed_batch(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS", "local")
    texts = ["Text 1", "Text 2", "Text 3"]
    batch = E.embed_batch(texts)
    assert len(batch) == 3
    for v in batch:
        assert v is not None
        assert len(v) == 1024


def test_pool_latency_stays_under_300ms(monkeypatch):
    """Pool p95 requirement: pre-computed embeddings cosine calculation is fast."""
    monkeypatch.setenv("EMBEDDINGS", "local")
    need_emb = E.embed_text("Backend engineer Python Django PostgreSQL")
    cand_embs = [E.embed_text(f"Candidate #{i} with python skills") for i in range(100)]

    start = time.perf_counter()
    for c_emb in cand_embs:
        assert c_emb is not None
        _ = F.cosine(need_emb, c_emb)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 300.0, f"100 candidate comparisons took {elapsed_ms:.2f} ms"
