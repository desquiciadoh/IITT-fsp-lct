"""Unit tests for schema validation and payload sanitization (AI-R3)."""
import json
from pathlib import Path

import pytest
from llm_gateway.base import LlmSchemaError
from llm_gateway.schema import validate_jd_payload, validate_resume_payload

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gigachat"


def test_schema_valid_resume():
    fixture_path = FIXTURES_DIR / "valid_resume.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    draft = validate_resume_payload(data)
    assert draft.specialization == "backend"
    assert draft.claimed_grade == "middle"
    assert draft.years_experience == 3.5
    assert draft.salary_min == 220000
    assert draft.salary_max == 280000
    assert draft.salary_type == "net"
    assert "Python" in draft.skills_raw
    assert draft.city == "Москва"


def test_schema_enum_synonym_normalization():
    fixture_path = FIXTURES_DIR / "invalid_enums.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    draft = validate_resume_payload(data)
    # 'бэкенд' -> 'backend'
    assert draft.specialization == "backend"
    # 'Ведущий' -> 'senior'
    assert draft.claimed_grade == "senior"
    # 'удаленка', 'в офисе' -> 'remote', 'office'
    assert "remote" in draft.work_formats
    assert "office" in draft.work_formats
    # 'на руки' -> 'net'
    assert draft.salary_type == "net"


def test_schema_string_salaries_and_swap():
    fixture_path = FIXTURES_DIR / "string_salaries_inverted.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    draft = validate_resume_payload(data)
    # '250 000' and '150к' with min > max should be swapped: 150000, 250000
    assert draft.salary_min == 150000
    assert draft.salary_max == 250000
    assert draft.years_experience == 1.5


def test_schema_caps_and_sanitization():
    raw = {
        "title": "A" * 300,
        "specialization": "backend",
        "grades": ["senior", "invalid_grade", "senior"],  # dedup and filter
        "must_skills_raw": ["Python" * 20, "FastAPI"],
        "nice_skills_raw": ["FastAPI", "Docker"],  # FastAPI already in must -> deduplicated
        "roles": ["Dev"] * 10,  # capped at 5
        "about": "B" * 700,  # capped at 500
        "description": "C" * 5000,  # capped at 4000
    }
    jd_draft = validate_jd_payload(raw)
    assert len(jd_draft.title) <= 200
    assert jd_draft.grades == ["senior"]
    assert "FastAPI" not in jd_draft.nice_skills_raw
    assert len(jd_draft.description) <= 4000


def test_schema_rejects_empty_or_non_dict():
    with pytest.raises(LlmSchemaError):
        validate_resume_payload([])  # type: ignore

    with pytest.raises(LlmSchemaError):
        validate_resume_payload({})  # no usable fields

    with pytest.raises(LlmSchemaError):
        validate_jd_payload({})
