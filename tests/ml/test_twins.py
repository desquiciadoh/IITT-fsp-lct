"""Unit tests for ML-12: Test Twins & screening blueprints. Pure: no Django."""
from __future__ import annotations

import math
import pytest

from assessment.engine.content import load_content
from assessment.engine.twins import create_test_twins, generate_twins_for_position
from assessment.families.base import GRADES, SPECS


def test_test_twins_structure_and_invariants():
    content = load_content()
    spec = "backend"
    skills = ["python", "postgresql", "docker"]
    grade = "middle"

    twins = create_test_twins(
        spec=spec,
        skills=skills,
        target_grade=grade,
        n_items=8,
        seed=2026,
        content=content,
    )

    # 1. Blueprint structure
    assert twins.spec == spec
    assert twins.target_grade == grade
    assert len(twins.twin_a.items) == 8
    assert len(twins.twin_b.items) == 8

    # 2. Both twins have identical topic distribution
    topics_a = [item.topic for item in twins.twin_a.items]
    topics_b = [item.topic for item in twins.twin_b.items]
    assert topics_a == topics_b

    # 3. Difficulty profile match: both twins target the target grade profile
    assert abs(twins.comparison.difficulty_diff) <= 0.35
    assert twins.comparison.identical_fingerprints == 0

    # 4. Invariant: Answer key is NEVER leaked in any item view
    for item in twins.twin_a.items + twins.twin_b.items:
        view = item.view
        assert "key" not in view
        assert "fingerprint" not in view
        assert "stem_md" in view
        assert "input" in view
        assert item.level in GRADES

    # 5. Distinct instances: for every slot, views should be distinct
    for item_a, item_b in zip(twins.twin_a.items, twins.twin_b.items):
        # Different fingerprints
        assert item_a.fingerprint != item_b.fingerprint


def test_test_twins_frontend_spec():
    twins = create_test_twins(
        spec="frontend",
        skills=["react", "typescript", "css"],
        target_grade="senior",
        n_items=6,
        seed=42,
    )

    assert twins.spec == "frontend"
    assert twins.target_grade == "senior"
    assert len(twins.twin_a.items) == 6
    assert len(twins.twin_b.items) == 6
    assert twins.comparison.identical_fingerprints == 0


def test_test_twins_ml_data_spec():
    twins = create_test_twins(
        spec="ml_data",
        skills=["pytorch", "pandas", "nlp"],
        target_grade="junior",
        n_items=8,
        seed=100,
    )

    assert twins.spec == "ml_data"
    assert twins.target_grade == "junior"
    assert len(twins.twin_a.items) == 8
    assert len(twins.twin_b.items) == 8


def test_generate_twins_for_position_dict():
    pos = {
        "position_id": "P-042",
        "title": "Senior Backend Developer",
        "specialization": "backend",
        "grades": ["senior"],
        "must_skills": ["python", "postgresql", "docker", "redis"],
        "nice_skills": ["kubernetes"],
    }

    twins = generate_twins_for_position(pos, seed=2026)
    assert twins.spec == "backend"
    assert twins.target_grade == "senior"
    assert len(twins.twin_a.items) >= 6
    d = twins.to_dict()
    assert "blueprint" in d
    assert "twin_a" in d
    assert "twin_b" in d
    assert "comparison" in d
    assert d["comparison"]["identical_fingerprints"] == 0
