"""Unit tests for Skill Taxonomy and normalization (AI-1, AI-R5)."""
from pathlib import Path

import yaml
from taxonomy import (
    extract_skills,
    get_skills_index,
    load_skills,
    normalize_many,
    normalize_skill,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_load_skills():
    catalog = load_skills()
    assert len(catalog) >= 100
    # Must preserve the 10 seed skills from AI-F3
    seed_ids = [
        "python", "django", "fastapi", "postgresql", "docker",
        "react", "typescript", "sql", "algorithms", "pytorch",
    ]
    for sid in seed_ids:
        assert sid in catalog, f"Seed skill '{sid}' must be in taxonomy"
        assert catalog[sid].name
        assert catalog[sid].topic


def test_skills_integrity():
    """Verify related ids exist and aliases are unique per AI-1."""
    catalog = load_skills()
    all_ids = set(catalog.keys())

    # 1. Related ids must exist
    for sid, entry in catalog.items():
        for rel in entry.related:
            assert rel in all_ids, f"Skill '{sid}' references non-existent related skill '{rel}'"

    # 2. Alias uniqueness (one alias -> one id)
    aliases: dict[str, str] = {}
    for sid, entry in catalog.items():
        for alias in entry.aliases:
            clean_a = alias.strip().lower()
            if clean_a in aliases:
                assert aliases[clean_a] == sid, (
                    f"Duplicate alias '{clean_a}' found in '{sid}' and '{aliases[clean_a]}'"
                )
            aliases[clean_a] = sid


def test_skills_index_o1_lookup():
    """Verify by_key index is populated and supports fast lookups."""
    by_key = get_skills_index()
    assert len(by_key) >= 200
    assert by_key.get("python") == "python"
    assert by_key.get("py") == "python"
    assert by_key.get("drf") == "drf"
    assert by_key.get("postgres") == "postgresql"


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
    assert normalize_skill("drf").skill_id == "drf"

    # Database aliases and typos
    assert normalize_skill("postgres").skill_id == "postgresql"
    assert normalize_skill("postgress").skill_id == "postgresql"
    assert normalize_skill("постгрес").skill_id == "postgresql"
    assert normalize_skill("постгря").skill_id == "postgresql"
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
    assert normalize_skill("си++").skill_id == "cpp"
    assert normalize_skill("с++").skill_id == "cpp"
    assert normalize_skill("плюсы").skill_id == "cpp"

    assert normalize_skill("C#").skill_id == "csharp"
    assert normalize_skill("c#").skill_id == "csharp"
    assert normalize_skill("с#").skill_id == "csharp"
    assert normalize_skill("си шарп").skill_id == "csharp"

    assert normalize_skill(".NET").skill_id == "dotnet"
    assert normalize_skill(".net").skill_id == "dotnet"
    assert normalize_skill("dot net").skill_id == "dotnet"

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


def test_skills_messy_fixture():
    """Verify >= 100 cases from skills_messy.yaml. Target >= 95% accuracy, 0 false positives on negatives."""
    messy_path = FIXTURES_DIR / "skills_messy.yaml"
    assert messy_path.exists(), "skills_messy.yaml must exist"

    with open(messy_path, "r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)

    assert len(cases) >= 100, f"Expected >= 100 cases, found {len(cases)}"

    correct = 0
    negatives = 0
    false_positives = 0
    failures = []

    for c in cases:
        raw = c["raw"]
        expected = c["expected"]
        m = normalize_skill(raw)
        actual = m.skill_id if m else None

        if expected is None:
            negatives += 1
            if actual is not None:
                false_positives += 1
                failures.append((raw, expected, actual))
        else:
            if actual == expected:
                correct += 1
            else:
                failures.append((raw, expected, actual))

    total = len(cases)
    accuracy = (total - len(failures)) / total * 100
    print(f"\nSkills messy accuracy: {accuracy:.2f}% ({total - len(failures)}/{total})")
    print(f"False positives on negatives: {false_positives}/{negatives}")

    assert false_positives == 0, f"Zero false positives required on negative set! Got {false_positives}"
    assert accuracy >= 95.0, f"Accuracy must be >= 95%, got {accuracy:.2f}%"
