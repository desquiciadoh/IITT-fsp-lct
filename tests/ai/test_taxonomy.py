"""Unit tests for Skill Taxonomy and normalization."""
import pytest
from apps.taxonomy import (
    extract_skills,
    load_skills,
    normalize_many,
    normalize_skill,
)


def test_load_skills():
    catalog = load_skills()
    assert len(catalog) >= 50
    # Must preserve the 10 seed skills from AI-F3
    seed_ids = [
        "python", "django", "fastapi", "postgresql", "docker",
        "react", "typescript", "sql", "algorithms", "pytorch",
    ]
    for sid in seed_ids:
        assert sid in catalog, f"Seed skill '{sid}' must be in taxonomy"
        assert catalog[sid].name
        assert catalog[sid].topic


def test_normalize_exact_and_aliases():
    # Exact canonical names
    assert normalize_skill("Python").skill_id == "python"
    assert normalize_skill("python").skill_id == "python"
    assert normalize_skill("Django").skill_id == "django"

    # Known aliases and transcriptions
    assert normalize_skill("py").skill_id == "python"
    assert normalize_skill("питон").skill_id == "python"
    assert normalize_skill("пайтон").skill_id == "python"
    assert normalize_skill("джанго").skill_id == "django"
    assert normalize_skill("drf").skill_id == "django"

    # Database aliases and typos
    assert normalize_skill("postgres").skill_id == "postgresql"
    assert normalize_skill("postgress").skill_id == "postgresql"
    assert normalize_skill("постгрес").skill_id == "postgresql"
    assert normalize_skill("k8s").skill_id == "kubernetes"
    assert normalize_skill("кубер").skill_id == "kubernetes"

    # Frontend aliases
    assert normalize_skill("ts").skill_id == "typescript"
    assert normalize_skill("тайпскрипт").skill_id == "typescript"
    assert normalize_skill("реакт").skill_id == "react"


def test_normalize_special_symbols():
    # C++, C#, .NET
    assert normalize_skill("C++").skill_id == "cpp"
    assert normalize_skill("c++").skill_id == "cpp"
    assert normalize_skill("плюсы").skill_id == "cpp"

    assert normalize_skill("C#").skill_id == "csharp"
    assert normalize_skill("c#").skill_id == "csharp"

    assert normalize_skill(".NET").skill_id == "dotnet"
    assert normalize_skill(".net").skill_id == "dotnet"

    assert normalize_skill("Node.js").skill_id == "nodejs"
    assert normalize_skill("node.js").skill_id == "nodejs"


def test_normalize_many_and_unknowns():
    raw_list = ["Python", "Django", "SuperCustomUnknownLib404", "k8s", ""]
    matches, unknowns = normalize_many(raw_list)

    matched_ids = [m.skill_id for m in matches]
    assert "python" in matched_ids
    assert "django" in matched_ids
    assert "kubernetes" in matched_ids

    assert unknowns == ["SuperCustomUnknownLib404"]


def test_extract_skills_from_text():
    text = "Ищем разработчика со знанием Python, FastAPI и PostgreSQL. Опыт с Docker и k8s приветствуется."
    matches, _ = extract_skills(text)
    matched_ids = {m.skill_id for m in matches}

    assert "python" in matched_ids
    assert "fastapi" in matched_ids
    assert "postgresql" in matched_ids
    assert "docker" in matched_ids
    assert "kubernetes" in matched_ids
