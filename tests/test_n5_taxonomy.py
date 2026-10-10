"""Tests for Task N5: Taxonomy sync, normalization, and API."""

import pytest
from core.enums import Specialization, UserRole
from django.core.management import call_command
from rest_framework.test import APIClient

from profiles.models import CandidateProfile, CandidateSkill, Skill


@pytest.mark.django_db
def test_sync_taxonomy_command():
    """Verify manage.py sync_taxonomy populates Skill rows from content/skills.yaml."""
    Skill.objects.all().delete()
    assert Skill.objects.count() == 0

    call_command("sync_taxonomy")
    assert Skill.objects.count() > 0

    py_skill = Skill.objects.filter(id="python").first()
    assert py_skill is not None
    assert py_skill.name == "Python"
    assert "py" in py_skill.aliases
    assert py_skill.topic == "backend.python"


@pytest.mark.django_db
def test_candidate_profile_skill_normalization_and_unknown_skills(django_user_model):
    """Verify profile update normalizes skills, links canonical skills, and collects unknown skills without creating Skill rows."""
    call_command("sync_taxonomy")
    initial_skills_count = Skill.objects.count()

    user = django_user_model.objects.create_user(
        email="cand_tax@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
    )
    profile = CandidateProfile.objects.create(
        user=user,
        specialization=Specialization.BACKEND,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    # Submit a mix of canonical, alias, and completely unknown skills
    payload = {
        "skills": ["py", "Питон", "джанго", "SuperCustomSkillUnknown123", "AnotherWeirdLang999"]
    }
    res = client.put("/api/candidates/me", payload, format="json")
    assert res.status_code == 200
    data = res.json()

    # Invariant: No arbitrary Skill rows were created from user input!
    assert Skill.objects.count() == initial_skills_count

    # Check unknown_skills in response and on profile
    assert "unknown_skills" in data
    assert "SuperCustomSkillUnknown123" in data["unknown_skills"]
    assert "AnotherWeirdLang999" in data["unknown_skills"]

    profile.refresh_from_db()
    assert "SuperCustomSkillUnknown123" in profile.unknown_skills
    assert "AnotherWeirdLang999" in profile.unknown_skills

    # Check candidate skills linked
    linked_skill_ids = set(profile.skills.values_list("skill_id", flat=True))
    assert "python" in linked_skill_ids
    assert "django" in linked_skill_ids


@pytest.mark.django_db
def test_get_taxonomy_endpoint_reads_yaml_and_registry():
    """Verify GET /api/taxonomy returns content from yaml and dynamically incorporates family registry topics."""
    client = APIClient()
    res = client.get("/api/taxonomy")
    assert res.status_code == 200
    data = res.json()

    # Check structure
    assert "specializations" in data
    assert "grades" in data
    assert "skills" in data
    assert "decline_reasons" in data

    # Check specializations have topics including registry topics
    backend_spec = next(s for s in data["specializations"] if s["id"] == "backend")
    assert "sql.aggregation" in backend_spec["topics"]
    assert "algorithms.complexity" in backend_spec["topics"]

    # Check grades
    grade_ids = [g["id"] for g in data["grades"]]
    assert "intern" in grade_ids
    assert "senior" in grade_ids

    # Check topics (ML-2)
    assert "topics" in data
    topic_ids = [t["id"] for t in data["topics"]]
    assert "algorithms.complexity" in topic_ids
    assert "sql.aggregation" in topic_ids

    # Check skills
    skill_ids = [s["id"] for s in data["skills"]]
    assert "python" in skill_ids
