import pytest
from assessment.models import LeagueMembership
from django.core.management import call_command
from django.core.management.base import CommandError
from fsp_sync.models import FSPLink, FSPResult
from fsp_sync.services import recompute_strength
from identity.models import User
from matching.models import Company, Position
from profiles.models import CandidateContact, CandidateProfile, CandidateSkill, Skill


@pytest.mark.django_db
def test_seed_idempotency_and_mode_full_rejection():
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

    # Verify mode=full is rejected with clean error
    with pytest.raises(CommandError, match="Full seed mode requires synthetic world data"):
        call_command("seed", mode="full")

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
