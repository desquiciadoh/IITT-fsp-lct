"""Test cases for gap endpoints: G3, G5, G6, G7, G11, G16."""

from datetime import timedelta

import pytest
from assessment.models import AssessmentItem, AssessmentSession, ItemFamily, LeagueMembership
from core.enums import (
    AssessmentStatus,
    ConsentType,
    DeclineReason,
    Grade,
    GradeDecision,
    ItemFormat,
    LeagueStatus,
    SalaryType,
    Specialization,
    UserRole,
)
from django.utils import timezone
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position, Shortlist
from profiles.models import CandidateProfile, CandidateSkill, Skill
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def item_families(db):
    ItemFamily.objects.get_or_create(
        id="be.sql.group_having.v1",
        defaults={
            "topic": "sql.aggregation",
            "specs": [Specialization.BACKEND],
            "format": ItemFormat.SQL_RESULT,
            "b": 0.4,
            "a": 1.2,
            "c": 0.25,
            "time_limit_s": 90,
        },
    )
    ItemFamily.objects.get_or_create(
        id="be.algo.complexity.v1",
        defaults={
            "topic": "algorithms.complexity",
            "specs": [Specialization.BACKEND],
            "format": ItemFormat.COMPLEXITY,
            "b": 0.8,
            "a": 1.2,
            "c": 0.25,
            "time_limit_s": 60,
        },
    )


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="cand.gap@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    profile = CandidateProfile.objects.create(
        user=user,
        public_id="CAN-GAP01",
        full_name="Алексей Смирнов",
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        salary_min=180000,
        salary_max=220000,
        open_to_offers=True,
    )
    python_skill, _ = Skill.objects.get_or_create(
        id="python", defaults={"name": "Python", "topic": "backend"}
    )
    django_skill, _ = Skill.objects.get_or_create(
        id="django", defaults={"name": "Django", "topic": "backend"}
    )
    CandidateSkill.objects.create(candidate=profile, skill=python_skill, source="test")
    CandidateSkill.objects.create(candidate=profile, skill=django_skill, source="test")

    Consent.objects.create(
        user=user,
        type=ConsentType.PUBLICATION,
        granted=True,
        version="v1.0",
    )

    LeagueMembership.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1150,
        confirmed_at=timezone.now(),
    )
    return user


@pytest.fixture
def candidate_client(candidate_user):
    client = APIClient()
    client.force_authenticate(user=candidate_user)
    return client


@pytest.fixture
def employer_with_position(db):
    emp_user = User.objects.create_user(
        email="employer.gap@example.com",
        password="password123",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(name="SuperTech LLC")
    CompanyMember.objects.create(company=company, user=emp_user)

    position = Position.objects.create(
        company=company,
        title="Middle Backend Developer",
        specialization=Specialization.BACKEND,
        grades=[Grade.MIDDLE, Grade.SENIOR],
        must_skills=["Python", "Django"],
        nice_skills=["Docker"],
        salary_min=160000,
        salary_max=240000,
        salary_type=SalaryType.GROSS,
        status="open",
    )
    client = APIClient()
    client.force_authenticate(user=emp_user)
    return emp_user, client, company, position


@pytest.mark.django_db
def test_g3_taxonomy_endpoint():
    """Verify G3: GET /api/taxonomy returns specializations, grades with rating cuts, skills, and decline reasons."""
    client = APIClient()
    res = client.get("/api/taxonomy")
    assert res.status_code == 200
    data = res.json()

    assert "specializations" in data
    assert "grades" in data
    assert "skills" in data
    assert "decline_reasons" in data

    spec_ids = [s["id"] for s in data["specializations"]]
    assert Specialization.BACKEND in spec_ids
    assert Specialization.FRONTEND in spec_ids
    assert Specialization.ML_DATA in spec_ids

    grade_cuts = {g["id"]: g["rating_cut"] for g in data["grades"]}
    assert grade_cuts[Grade.INTERN] == 800
    assert grade_cuts[Grade.JUNIOR] == 960
    assert grade_cuts[Grade.MIDDLE] == 1120
    assert grade_cuts[Grade.SENIOR] == 1300

    decline_codes = [dr["id"] for dr in data["decline_reasons"]]
    assert DeclineReason.SALARY in decline_codes


@pytest.mark.django_db
def test_g6_position_parse_endpoint(employer_with_position):
    """Verify G6: POST /api/positions/parse returns draft, blueprint, and unknown_terms."""
    _, client, _, _ = employer_with_position

    jd_text = (
        "Ищем опытного Senior Python разработчика в команду Backend. "
        "Требуется отличный опыт с Django, Docker, PostgreSQL, Celery. "
        "Зарплатная вилка от 250000 до 350000 руб. "
        "Формат работы: удаленка или гибрид в Москве."
    )

    res = client.post("/api/positions/parse", {"raw_text": jd_text}, format="json")
    assert res.status_code == 200
    data = res.json()

    assert "draft" in data
    assert "blueprint" in data
    assert "source" in data
    assert data["source"] == "rules"

    draft = data["draft"]
    assert draft["specialization"] == Specialization.BACKEND
    assert Grade.SENIOR in draft["grades"]
    assert "python" in draft["must_skills"]
    assert "django" in draft["must_skills"]
    assert draft["salary_min"] == 250000
    assert draft["salary_max"] == 350000
    assert draft["location"] == "Москва"


@pytest.mark.django_db
def test_g7_leagues_endpoint(candidate_client, candidate_user):
    """Verify G7: GET /api/leagues returns shelves with candidate counts and median salary expectation."""
    # Add a second candidate to test median calculation
    user2 = User.objects.create_user(
        email="cand2.gap@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user2,
        public_id="CAN-GAP02",
        full_name="Дмитрий Иванов",
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        salary_min=200000,
        salary_max=250000,
        open_to_offers=True,
    )
    LeagueMembership.objects.create(
        candidate=user2,
        specialization=Specialization.BACKEND,
        grade=Grade.MIDDLE,
        status=LeagueStatus.CONFIRMED,
        rating=1140,
        confirmed_at=timezone.now(),
    )

    res = candidate_client.get("/api/leagues?specialization=backend")
    assert res.status_code == 200
    shelves = res.json()
    assert isinstance(shelves, list)

    middle_shelf = next(
        (
            s
            for s in shelves
            if s["grade"] == Grade.MIDDLE and s["specialization"] == Specialization.BACKEND
        ),
        None,
    )
    assert middle_shelf is not None
    assert middle_shelf["confirmed"] >= 2
    # Median of 180000 and 200000 is 190000
    assert middle_shelf["median_expectation"] == 190000


@pytest.mark.django_db
def test_g11_lab_report_endpoint():
    """Verify G11: GET /api/lab/report returns validation metrics report fixture."""
    client = APIClient()
    res = client.get("/api/lab/report")
    assert res.status_code == 200
    data = res.json()

    assert "generated_at" in data
    assert "git_sha" in data
    assert "synthetic_fixture" in data
    assert data.get("synthetic_fixture") is True

    assert "assessment" in data
    assert "matching" in data
    assert data["assessment"]["simulees"] == 1000
    assert data["assessment"]["exact_acc"] >= 0.8
    assert len(data["matching"]["systems"]) >= 2


@pytest.mark.django_db
def test_g16_position_shortlist_endpoint(employer_with_position, candidate_user):
    """Verify G16: GET /api/positions/{id}/shortlist returns shortlisted candidates."""
    _, client, _, position = employer_with_position

    Shortlist.objects.create(position=position, candidate=candidate_user)

    res = client.get(f"/api/positions/{position.id}/shortlist")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert len(items) >= 1

    item = items[0]
    assert item["public_id"] == "CAN-GAP01"
    assert item["display_name"] == "Алексей Смирнов"
    assert item["league"]["grade"] == Grade.MIDDLE
    assert isinstance(item["verified_topics"], list)


def _unconfirmed_senior_session(user, corrects):
    """Finished, unconfirmed Senior session whose items were answered with `corrects`.

    Items use the fixture families (b=0.4, b=0.8): 1 of 2 correct re-scores to
    theta 0.6 = Middle, 0 of 2 to -0.4 = Intern.
    """
    session = AssessmentSession.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.SENIOR,
        mode="full",
        status=AssessmentStatus.FINISHED,
        decision=GradeDecision.UNCONFIRMED,
        theta=0.6,
        se=0.71,
        rating=1120,
        finished_at=timezone.now(),
    )
    family_ids = ["be.sql.group_having.v1", "be.algo.complexity.v1"]
    for seq, (family_id, correct) in enumerate(zip(family_ids, corrects, strict=True), start=1):
        AssessmentItem.objects.create(
            assessment=session,
            seq=seq,
            family_id=family_id,
            seed=f"seed-{seq}",
            view={"stem_md": "q", "options": [], "input_type": "choice", "time_limit_s": 60},
            key="o1",
            answer={"value": "o1" if correct else "o2"},
            correct=correct,
            answered_at=timezone.now(),
            deadline_at=timezone.now(),
        )
    return session


@pytest.mark.django_db
def test_g5_assessment_fallback_instant(candidate_user, candidate_client):
    """G5 instant fallback: confirms the lower grade when the same answers support it."""
    session = _unconfirmed_senior_session(candidate_user, corrects=[True, False])

    membership, _ = LeagueMembership.objects.get_or_create(
        candidate=candidate_user,
        specialization=Specialization.BACKEND,
        defaults={
            "grade": Grade.SENIOR,
            "status": LeagueStatus.UNCONFIRMED,
            "next_attempt_at": timezone.now() + timedelta(days=30),
        },
    )
    membership.grade = Grade.SENIOR
    membership.status = LeagueStatus.UNCONFIRMED
    membership.next_attempt_at = timezone.now() + timedelta(days=30)
    membership.save()

    # Post instant fallback
    res = candidate_client.post(
        f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json"
    )
    assert res.status_code == 200
    data = res.json()

    assert data["result_grade"] == Grade.MIDDLE
    assert data["decision"] == GradeDecision.CONFIRMED

    # Verify LeagueMembership updated to CONFIRMED at Middle grade, cooldown cleared
    membership.refresh_from_db()
    assert membership.grade == Grade.MIDDLE
    assert membership.status == LeagueStatus.CONFIRMED
    assert membership.next_attempt_at is None


@pytest.mark.django_db
def test_g5_assessment_fallback_instant_not_eligible(candidate_user, candidate_client):
    """G5 instant fallback is refused (409) when the answers do not support the lower grade."""
    session = _unconfirmed_senior_session(candidate_user, corrects=[False, False])
    membership = LeagueMembership.objects.get(
        candidate=candidate_user, specialization=Specialization.BACKEND
    )
    membership.status = LeagueStatus.UNCONFIRMED
    membership.next_attempt_at = timezone.now() + timedelta(days=30)
    membership.save()
    cooldown = membership.next_attempt_at

    res = candidate_client.post(
        f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json"
    )

    assert res.status_code == 409
    assert res.json()["code"] == "fallback_not_eligible"
    session.refresh_from_db()
    assert session.decision == GradeDecision.UNCONFIRMED
    membership.refresh_from_db()
    assert membership.status == LeagueStatus.UNCONFIRMED
    assert membership.next_attempt_at == cooldown


@pytest.mark.django_db
def test_g5_result_offers_only_an_allowed_fallback(candidate_user, candidate_client):
    """The result screen must not advertise instant when the service would refuse it."""
    eligible = _unconfirmed_senior_session(candidate_user, corrects=[True, False])
    res = candidate_client.get(f"/api/assessments/{eligible.id}/result")
    assert res.json()["fallback"] == {"grade": Grade.MIDDLE, "mode": "instant"}

    eligible.delete()
    ineligible = _unconfirmed_senior_session(candidate_user, corrects=[False, False])
    res = candidate_client.get(f"/api/assessments/{ineligible.id}/result")
    assert res.json()["fallback"] == {"grade": Grade.MIDDLE, "mode": "short_test"}


@pytest.mark.django_db
def test_g5_assessment_fallback_short_test(candidate_user, candidate_client):
    """Verify G5 short_test fallback: creates new express assessment session at lower grade."""
    session = AssessmentSession.objects.create(
        candidate=candidate_user,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.SENIOR,
        mode="full",
        status=AssessmentStatus.FINISHED,
        decision=GradeDecision.UNCONFIRMED,
        theta=0.1,
        se=0.3,
        rating=1050,
        finished_at=timezone.now(),
    )

    res = candidate_client.post(
        f"/api/assessments/{session.id}/fallback", {"mode": "short_test"}, format="json"
    )
    assert res.status_code == 201
    new_session_data = res.json()

    assert new_session_data["claimed_grade"] == Grade.MIDDLE
    assert new_session_data["mode"] == "express"
    assert new_session_data["status"] == AssessmentStatus.IN_PROGRESS


@pytest.mark.django_db
def test_g8_position_pool_filtering_facets_and_components(employer_with_position, candidate_user):
    """Verify G8: PositionPoolView returns query-filtered candidates, facets, components list, and gaps."""
    _, client, company, position = employer_with_position

    # Add FSP result for candidate_user to test fsp filter and boost
    from core.enums import Discipline, PlacementTier
    from fsp_sync.models import FSPResult

    FSPResult.objects.create(
        candidate=candidate_user,
        event_id="EVT-01",
        event_name="All-Russian FSP Hackathon",
        discipline=Discipline.ALGORITHMIC,
        date="2025-10-01",
        placement=1,
        tier=PlacementTier.WINNER,
        participants_total=100,
    )

    # 1. Fetch pool without filters
    res = client.get(f"/api/positions/{position.id}/pool")
    assert res.status_code == 200
    data = res.json()

    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "pages" in data
    assert "facets" in data
    assert "relaxations" in data
    assert data["total"] >= 1

    item = data["items"][0]
    assert "talent" in item
    assert "score" in item
    assert "components" in item
    assert "reasons" in item
    assert "gaps" in item
    assert "shortlisted" in item

    # Verify G8 components list shape: [{key, value, weight, contribution}]
    components = item["components"]
    assert isinstance(components, list)
    assert len(components) == 5
    for comp in components:
        assert "key" in comp
        assert "value" in comp
        assert "weight" in comp
        assert "contribution" in comp

    # Verify facets structure
    facets = data["facets"]
    assert "grades" in facets
    assert "formats" in facets
    assert "fsp_total" in facets

    # 2. Test query filters: e.g. fsp=true
    res_fsp = client.get(f"/api/positions/{position.id}/pool?fsp=true")
    assert res_fsp.status_code == 200
    assert res_fsp.json()["total"] >= 1

    # Test query filter: salary_max=100000 (candidate has 180000 min, so should be 0)
    res_sal = client.get(f"/api/positions/{position.id}/pool?salary_max=100000")
    assert res_sal.status_code == 200
    assert res_sal.json()["total"] == 0

    # Test pagination: page=1, size=1
    res_paged = client.get(f"/api/positions/{position.id}/pool?page=1&size=1")
    assert res_paged.status_code == 200
    paged_data = res_paged.json()
    assert paged_data["page"] == 1
    assert len(paged_data["items"]) <= 1


@pytest.mark.django_db
def test_g14_consistent_pagination(employer_with_position, candidate_user, candidate_client):
    """Verify G14: Consistent {items, total, page, pages} on /offers, /assessments, and /talent/search."""
    _, employer_client, _, _ = employer_with_position

    # 1. GET /api/talent/search
    res_search = employer_client.get("/api/talent/search?page=1&size=10")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert "items" in search_data
    assert "total" in search_data
    assert "page" in search_data
    assert "pages" in search_data
    assert isinstance(search_data["items"], list)

    # 2. GET /api/assessments
    AssessmentSession.objects.create(
        candidate=candidate_user,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        mode="full",
        status=AssessmentStatus.FINISHED,
    )
    res_assess = candidate_client.get("/api/assessments?page=1&size=10")
    assert res_assess.status_code == 200
    assess_data = res_assess.json()
    assert "items" in assess_data
    assert "total" in assess_data
    assert "page" in assess_data
    assert "pages" in assess_data
    assert assess_data["total"] >= 1

    # 3. GET /api/offers
    res_offers = candidate_client.get("/api/offers?page=1&size=10")
    assert res_offers.status_code == 200
    offers_data = res_offers.json()
    assert "items" in offers_data
    assert "total" in offers_data
    assert "page" in offers_data
    assert "pages" in offers_data


@pytest.mark.django_db
def test_g9_talent_detail_and_blind_mode(employer_with_position, candidate_user):
    """Verify G9: TalentCard returns topics, fsp_results, assessments, integrity_flags, and contacts."""
    _, client, _, _ = employer_with_position
    profile = candidate_user.candidate_profile

    res = client.get(f"/api/talent/{profile.public_id}")
    assert res.status_code == 200
    card = res.json()

    assert card["public_id"] == profile.public_id
    assert card["display_name"] == profile.full_name
    assert "topics" in card
    assert "fsp_results" in card
    assert "assessments" in card
    assert "integrity_flags" in card
    # Contacts should be None/unmasked since no active ContactGrant
    assert card["contacts"] is None

    # Test blind mode alias
    profile.blind_mode = True
    profile.save()
    res_blind = client.get(f"/api/talent/{profile.public_id}")
    assert res_blind.status_code == 200
    assert res_blind.json()["display_name"] == f"Кандидат {profile.public_id}"


@pytest.mark.django_db
def test_g10_offer_serializer_talent_short_and_decline(
    employer_with_position, candidate_user, candidate_client
):
    """Verify G10: Offer includes talent: TalentShort and decline: {reason, comment}."""
    emp_user, emp_client, company, position = employer_with_position
    profile = candidate_user.candidate_profile

    # Employer creates an offer
    offer_payload = {
        "candidate_public_id": profile.public_id,
        "position": str(position.id),
        "title": "Senior Python Dev",
        "salary_min": 200000,
        "salary_max": 250000,
        "salary_type": "gross",
        "contact_channel": "telegram",
        "contact_value": "@smirnov_dev",
    }
    create_res = emp_client.post("/api/offers", offer_payload, format="json")
    assert create_res.status_code == 201
    offer_data = create_res.json()

    assert "talent" in offer_data
    assert offer_data["talent"]["public_id"] == profile.public_id
    assert offer_data["talent"]["display_name"] == profile.full_name
    assert offer_data["decline"] is None

    offer_id = offer_data["id"]
    version = offer_data["version"]

    # Candidate views the offer first: SENT -> VIEWED
    view_res = candidate_client.post(
        f"/api/offers/{offer_id}/view",
        {"version": version},
        format="json",
    )
    assert view_res.status_code == 200
    version = view_res.json()["version"]

    # Candidate declines the offer with a reason: VIEWED -> DECLINED
    decline_res = candidate_client.post(
        f"/api/offers/{offer_id}/decline",
        {
            "version": version,
            "reason": DeclineReason.SALARY,
            "comment": "Предложение ниже ожиданий",
        },
        format="json",
    )
    assert decline_res.status_code == 200
    declined_offer = decline_res.json()

    assert declined_offer["decline"] is not None
    assert declined_offer["decline"]["reason"] == DeclineReason.SALARY
    assert declined_offer["decline"]["comment"] == "Предложение ниже ожиданий"
