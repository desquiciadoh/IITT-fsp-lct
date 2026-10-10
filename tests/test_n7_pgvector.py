"""Tests for Task N7: pgvector VectorField(1024) and HNSW indexes."""

import pytest
from django.db import connection
from identity.models import User
from matching.models import Company, Position
from pgvector.django import CosineDistance
from profiles.models import CandidateProfile


@pytest.mark.django_db
def test_candidate_profile_embedding_storage_and_retrieval():
    user = User.objects.create(email="embed_candidate@example.com", role="candidate")
    profile = CandidateProfile.objects.create(user=user)

    # 1024-dimensional vector
    vec = [0.0] * 1024
    vec[0] = 1.0
    vec[1023] = 0.5
    profile.embedding = vec
    profile.save(update_fields=["embedding"])

    reloaded = CandidateProfile.objects.get(user=user)
    assert reloaded.embedding is not None
    assert len(reloaded.embedding) == 1024
    assert pytest.approx(reloaded.embedding[0]) == 1.0
    assert pytest.approx(reloaded.embedding[1023]) == 0.5


@pytest.mark.django_db
def test_position_embedding_storage_and_retrieval():
    company = Company.objects.create(name="Vector Tech")
    pos = Position.objects.create(
        company=company,
        title="ML Engineer",
        specialization="backend",
        grades=["middle"],
        salary_min=150000,
        salary_max=250000,
        salary_type="gross",
    )

    vec = [0.1] * 1024
    vec[500] = 0.9
    pos.embedding = vec
    pos.save(update_fields=["embedding"])

    reloaded = Position.objects.get(id=pos.id)
    assert reloaded.embedding is not None
    assert len(reloaded.embedding) == 1024
    assert pytest.approx(reloaded.embedding[500]) == 0.9


@pytest.mark.django_db
def test_pgvector_cosine_distance_query():
    user1 = User.objects.create(email="c1@example.com", role="candidate")
    user2 = User.objects.create(email="c2@example.com", role="candidate")

    vec1 = [0.0] * 1024
    vec1[0] = 1.0  # vector [1, 0, 0, ...]
    profile1 = CandidateProfile.objects.create(user=user1, embedding=vec1)

    vec2 = [0.0] * 1024
    vec2[1] = 1.0  # orthogonal vector [0, 1, 0, ...]
    profile2 = CandidateProfile.objects.create(user=user2, embedding=vec2)

    query_vec = [0.0] * 1024
    query_vec[0] = 1.0

    nearest = (
        CandidateProfile.objects.filter(embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", query_vec))
        .order_by("distance")
    )

    results = list(nearest)
    assert len(results) >= 2
    assert results[0].user_id == profile1.user_id
    assert pytest.approx(results[0].distance, abs=1e-5) == 0.0
    assert results[1].user_id == profile2.user_id
    assert pytest.approx(results[1].distance, abs=1e-5) == 1.0


@pytest.mark.django_db
def test_hnsw_indexes_exist_in_database():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname, tablename, indexdef
            FROM pg_indexes
            WHERE indexname IN ('candidate_profile_emb_hnsw', 'position_embedding_hnsw')
            """
        )
        rows = cursor.fetchall()

    indexes = {row[0]: (row[1], row[2]) for row in rows}
    assert "candidate_profile_emb_hnsw" in indexes
    assert "position_embedding_hnsw" in indexes
    assert "hnsw" in indexes["candidate_profile_emb_hnsw"][1].lower()
    assert "hnsw" in indexes["position_embedding_hnsw"][1].lower()
