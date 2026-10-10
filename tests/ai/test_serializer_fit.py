"""The parse results must fit the real serializers (AI-R11). Needs PostgreSQL (ArrayField)."""
from pathlib import Path

import llm_gateway.resume
import pytest
from core.enums import UserRole
from django.utils import timezone
from identity.models import User
from llm_gateway import FakeLlm, parse_jd, parse_resume
from matching.serializers import PositionSerializer
from profiles.models import CandidateProfile, generate_public_id
from profiles.serializers import CandidateProfileUpdateSerializer

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
HERO_CVS = ["cv_backend_middle.pdf", "cv_frontend_junior.pdf", "cv_ml_senior.pdf"]
JDS = sorted(p.name for p in (FIXTURES_DIR / "jd").glob("*.txt"))
REQUIRED_POSITION_FIELDS = ("title", "specialization", "grades", "salary_min", "salary_max", "salary_type")


@pytest.fixture
def profile(db):
    user = User.objects.create_user(
        email="fit@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    return CandidateProfile.objects.create(user=user, public_id=generate_public_id())


@pytest.mark.django_db
@pytest.mark.parametrize("cv", HERO_CVS)
def test_resume_prefill_fits_profile_serializer(profile, cv):
    prefill = parse_resume((FIXTURES_DIR / "cv" / cv).read_bytes(), gateway=FakeLlm()).prefill

    serializer = CandidateProfileUpdateSerializer(instance=profile, data=prefill, partial=True)

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_unknown_values_fit_profile_serializer(profile, monkeypatch):
    """Nothing recognised: "" / [] / None, never a null in a non-null CharField."""
    monkeypatch.setattr(llm_gateway.resume, "extract_text", lambda _: "Текст без полезных данных")
    prefill = parse_resume(b"%PDF", gateway=FakeLlm()).prefill

    assert prefill["specialization"] == prefill["claimed_grade"] == prefill["salary_type"] == ""
    serializer = CandidateProfileUpdateSerializer(instance=profile, data=prefill, partial=True)
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize("jd", JDS)
def test_jd_draft_fits_position_serializer(jd):
    """Errors only for required fields the JD does not state (the form asks for them)."""
    draft = parse_jd((FIXTURES_DIR / "jd" / jd).read_text(encoding="utf-8"), gateway=FakeLlm()).draft

    serializer = PositionSerializer(data=draft)
    serializer.is_valid()

    unknown = {f for f in REQUIRED_POSITION_FIELDS if draft[f] in ("", [], None)}
    assert set(serializer.errors) <= unknown, serializer.errors
