import pytest
from assessment.models import LeagueMembership
from django.core.management import call_command
from fsp_sync.models import FSPLink, FSPResult
from fsp_sync.services import recompute_strength
from identity.models import User
from matching.models import Company, Position
from profiles.models import CandidateContact, CandidateProfile, CandidateSkill, Skill


@pytest.mark.django_db
def test_seed_mini_idempotency():
    # First seed
    call_command("seed", mode="mini")

    counts_first = {
        "users": User.objects.count(),
        "profiles": CandidateProfile.objects.count(),
        "contacts": CandidateContact.objects.count(),
        "skills": Skill.objects.count(),
        "candidate_skills": CandidateSkill.objects.count(),
        "leagues": LeagueMembership.objects.count(),
        "companies": Company.objects.count(),
        "positions": Position.objects.count(),
        "fsp_links": FSPLink.objects.count(),
        "fsp_results": FSPResult.objects.count(),
    }

    # Second seed
    call_command("seed", mode="mini")

    counts_second = {
        "users": User.objects.count(),
        "profiles": CandidateProfile.objects.count(),
        "contacts": CandidateContact.objects.count(),
        "skills": Skill.objects.count(),
        "candidate_skills": CandidateSkill.objects.count(),
        "leagues": LeagueMembership.objects.count(),
        "companies": Company.objects.count(),
        "positions": Position.objects.count(),
        "fsp_links": FSPLink.objects.count(),
        "fsp_results": FSPResult.objects.count(),
    }

    assert counts_first == counts_second, (
        f"Counts differ between seed runs: {counts_first} != {counts_second}"
    )

    # Verify passwords are unusable for security
    for user in User.objects.filter(is_demo=True):
        assert not user.has_usable_password(), f"User {user.email} should have unusable password"

    # Verify Anna's strength idempotency
    anna = User.objects.get(email="anna.fsp@example.com")
    mem = LeagueMembership.objects.get(candidate=anna)
    assert mem.strength == 95.0
    assert mem.base_strength == 85.0
    assert mem.fsp_boost == 10.0

    # Running recompute_strength gives exact same values
    mem_after = recompute_strength(anna)
    assert mem_after.strength == 95.0
    assert mem_after.base_strength == 85.0
    assert mem_after.fsp_boost == 10.0


@pytest.mark.django_db
def test_seed_mode_full():
    # First full seed run
    call_command("seed", mode="full")

    # Check companies from companies.jsonl
    polar = Company.objects.get(name="Полярный код")
    sever = Company.objects.get(name="Северные системы")
    assert polar.email_domain == "polar-code.example"
    assert polar.members.count() == 1
    assert sever.members.count() == 1

    # Check positions from positions.jsonl
    assert Position.objects.filter(company=polar).exists()
    assert Position.objects.filter(company=sever).exists()

    # Check candidates from candidates.jsonl (hero Anna)
    anna = User.objects.get(email="anna.fsp@example.com")
    assert anna.is_demo is True
    assert not anna.has_usable_password()
    assert anna.email_verified_at is not None

    profile = CandidateProfile.objects.get(user=anna)
    assert profile.public_id == "C-4325C3A7"
    assert profile.specialization == "backend"
    assert profile.claimed_grade == "senior"

    # Contact gating table
    contact = CandidateContact.objects.get(user=anna)
    assert contact.telegram == "@anna"

    # Consents
    assert anna.consents.filter(type="publication", granted=True).exists()
    assert anna.consents.filter(type="fsp_sync", granted=True).exists()

    # League
    league = LeagueMembership.objects.get(candidate=anna, specialization="backend")
    assert league.rating == 1294
    assert league.strength == 58.97

    # FSP Link & Results
    fsp_link = FSPLink.objects.get(candidate=anna)
    assert fsp_link.participant_id == "FSP-111778"
    assert FSPResult.objects.filter(candidate=anna).count() == 2

    counts_first = {
        "users": User.objects.count(),
        "profiles": CandidateProfile.objects.count(),
        "contacts": CandidateContact.objects.count(),
        "companies": Company.objects.count(),
        "positions": Position.objects.count(),
        "leagues": LeagueMembership.objects.count(),
        "fsp_links": FSPLink.objects.count(),
        "fsp_results": FSPResult.objects.count(),
    }

    # Second full seed run must be completely idempotent
    call_command("seed", mode="full")

    counts_second = {
        "users": User.objects.count(),
        "profiles": CandidateProfile.objects.count(),
        "contacts": CandidateContact.objects.count(),
        "companies": Company.objects.count(),
        "positions": Position.objects.count(),
        "leagues": LeagueMembership.objects.count(),
        "fsp_links": FSPLink.objects.count(),
        "fsp_results": FSPResult.objects.count(),
    }

    assert counts_first == counts_second, (
        f"Counts differ between full seed runs: {counts_first} != {counts_second}"
    )
