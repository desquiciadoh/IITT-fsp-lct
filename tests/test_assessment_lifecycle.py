"""Assessment lifecycle: per-item deadlines, late answers, fallback eligibility, one active session.

Rewritten for the real ML CAT engine (N2, IrtCatEngine via cat_bridge):
- serve-one-item-at-a-time (ML-3): start() creates exactly ONE item; the next
  item appears only after the previous answer is recorded;
- theta/se come from EAP on the fixed-c 3PL model, not the legacy placeholder
  formula; grade assertions below rely on engine `result_grade` semantics
  (fallback eligibility replays the session's own answers through the engine);
- family time limits govern live deadlines (ML.md §3).
"""

from datetime import timedelta
from unittest import mock

import pytest
from assessment.models import AssessmentItem, AssessmentSession, LeagueMembership
from assessment.services import DEADLINE_GRACE_S, AssessmentService
from core.enums import (
    AssessmentStatus,
    Grade,
    GradeDecision,
    LeagueStatus,
    Specialization,
    UserRole,
)
from core.errors import AssessmentInProgress
from django.db import IntegrityError, transaction
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture
def cand(db):
    return User.objects.create_user(
        email="lifecycle@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def client(cand):
    c = APIClient()
    c.force_authenticate(user=cand)
    return c


def _start(cand, grade=Grade.SENIOR):
    return AssessmentService.start_assessment(cand, Specialization.BACKEND, grade)


def _items(session):
    return list(AssessmentItem.objects.filter(assessment=session).order_by("seq"))


def _wrong(item):
    return next(o["id"] for o in item.view["options"] if o["id"] != item.key)


def _answer(client, session, item, value):
    return client.post(
        f"/api/assessments/{session.id}/answers",
        {"item_id": str(item.id), "option_id": value},
        format="json",
    )


def _expire(item, seconds_ago):
    item.deadline_at = timezone.now() - timedelta(seconds=seconds_ago)
    item.save(update_fields=["deadline_at"])


# --- Bug 1: deadlines are per served item; a late answer never rolls the session back ---


def test_start_sets_deadline_only_for_first_item(cand):
    before = timezone.now()
    session = _start(cand)
    first, second = _items(session)

    assert first.deadline_at is not None
    assert (
        before + timedelta(seconds=90)
        <= first.deadline_at
        <= timezone.now() + timedelta(seconds=90)
    )
    assert second.deadline_at is None


def test_next_item_deadline_starts_when_it_is_served(cand, client):
    session = _start(cand)
    first, second = _items(session)

    before = timezone.now()
    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    body = res.json()
    assert body["done"] is False
    assert body["next"]["item_id"] == str(second.id)
    assert body["next"]["deadline_at"] is not None
    second.refresh_from_db()
    assert (
        before + timedelta(seconds=60)
        <= second.deadline_at
        <= timezone.now() + timedelta(seconds=60)
    )
    assert second.served_at >= before

    detail = client.get(f"/api/assessments/{session.id}").json()
    assert detail["current"]["item_id"] == str(second.id)
    assert detail["current"]["deadline_at"] is not None
    assert "key" not in detail["current"]


def test_late_answer_is_recorded_wrong_and_test_continues(cand, client):
    session = _start(cand)
    first, second = _items(session)
    _expire(first, DEADLINE_GRACE_S + 10)

    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    assert res.json()["done"] is False
    assert res.json()["next"]["item_id"] == str(second.id)
    first.refresh_from_db()
    assert first.correct is False
    assert first.answer == {"value": None, "timed_out": True, "late": True}
    session.refresh_from_db()
    assert session.status == AssessmentStatus.IN_PROGRESS

    # Retrying the late item is a normal 409, not a stuck 400.
    retry = _answer(client, session, first, first.key)
    assert retry.status_code == 409
    assert retry.json()["code"] == "item_not_current"


def test_answer_within_grace_counts(cand, client):
    session = _start(cand)
    first, _ = _items(session)
    _expire(first, 1)

    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    first.refresh_from_db()
    assert first.correct is True
    assert first.answer == {"value": first.key}


def test_late_last_item_finalizes_session(cand, client):
    session = _start(cand)
    first, second = _items(session)
    assert _answer(client, session, first, first.key).status_code == 200
    second.refresh_from_db()
    _expire(second, DEADLINE_GRACE_S + 10)

    res = _answer(client, session, second, second.key)

    assert res.status_code == 200
    body = res.json()
    assert body["done"] is True
    session.refresh_from_db()
    assert session.status == AssessmentStatus.FINISHED
    assert session.finished_at is not None
    second.refresh_from_db()
    assert second.correct is False
    assert second.answer["late"] is True
    # 1/2 correct -> theta 0.6 (Middle) < claimed Senior
    assert session.decision == GradeDecision.UNCONFIRMED


# --- Bug 2: instant fallback needs evidence from the same answers; short_test once ---


def _finish_senior(cand, client, correct_first=True, correct_second=False):
    session = _start(cand, Grade.SENIOR)
    first, second = _items(session)
    _answer(client, session, first, first.key if correct_first else _wrong(first))
    second.refresh_from_db()
    res = _answer(client, session, second, second.key if correct_second else _wrong(second))
    assert res.json()["done"] is True
    session.refresh_from_db()
    assert session.decision == GradeDecision.UNCONFIRMED
    return session


def test_instant_fallback_confirms_when_answers_support_lower_grade(cand, client):
    session = _finish_senior(cand, client, correct_first=True)  # theta 0.6 -> Middle

    res = client.post(f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json")

    assert res.status_code == 200
    assert res.json()["result_grade"] == Grade.MIDDLE
    assert res.json()["decision"] == GradeDecision.CONFIRMED
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    assert lm.grade == Grade.MIDDLE
    assert lm.status == LeagueStatus.CONFIRMED
    assert lm.next_attempt_at is None


def test_instant_fallback_refused_when_answers_do_not_support_lower_grade(cand, client):
    session = _finish_senior(cand, client, correct_first=False)  # theta -0.4 -> Intern
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    cooldown = lm.next_attempt_at
    assert cooldown is not None

    res = client.post(f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json")

    assert res.status_code == 409
    assert res.json()["code"] == "fallback_not_eligible"
    assert "short_test" in res.json()["detail"]
    lm.refresh_from_db()
    assert lm.next_attempt_at == cooldown
    assert lm.status == LeagueStatus.UNCONFIRMED
    session.refresh_from_db()
    assert session.decision == GradeDecision.UNCONFIRMED


def test_instant_fallback_refused_after_abandon(cand, client):
    session = _start(cand, Grade.SENIOR)
    first, _ = _items(session)
    _answer(client, session, first, first.key)  # 1/2 correct would rescore to Middle
    assert client.post(f"/api/assessments/{session.id}/finish").status_code == 200
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    cooldown = lm.next_attempt_at

    res = client.post(f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json")

    assert res.status_code == 409
    assert res.json()["code"] == "fallback_not_eligible"
    lm.refresh_from_db()
    assert lm.next_attempt_at == cooldown


def test_short_test_fallback_usable_once(cand, client):
    session = _finish_senior(cand, client, correct_first=False)

    first = client.post(
        f"/api/assessments/{session.id}/fallback", {"mode": "short_test"}, format="json"
    )
    assert first.status_code == 201
    short_id = first.json()["id"]
    assert client.post(f"/api/assessments/{short_id}/finish").status_code == 200
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    cooldown = lm.next_attempt_at

    again = client.post(
        f"/api/assessments/{session.id}/fallback", {"mode": "short_test"}, format="json"
    )

    assert again.status_code == 409
    assert again.json()["code"] == "fallback_already_used"
    lm.refresh_from_db()
    assert lm.next_attempt_at == cooldown
    assert AssessmentSession.objects.filter(candidate=cand, claimed_grade=Grade.MIDDLE).count() == 1


# --- Bug 3: at most one in-progress session per candidate and specialization ---


def test_db_rejects_second_in_progress_session(cand):
    AssessmentSession.objects.create(
        candidate=cand,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AssessmentSession.objects.create(
            candidate=cand,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.SENIOR,
        )
    # Other specializations and closed sessions are unaffected.
    AssessmentSession.objects.create(
        candidate=cand,
        specialization=Specialization.FRONTEND,
        claimed_grade=Grade.MIDDLE,
    )
    for _ in range(2):
        AssessmentSession.objects.create(
            candidate=cand,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            status=AssessmentStatus.FINISHED,
        )


def test_start_maps_race_to_assessment_in_progress(cand):
    """Simulate the race: the pre-check sees nothing, the insert hits the constraint."""
    existing = AssessmentSession.objects.create(
        candidate=cand,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
    )
    empty = mock.Mock()
    empty.filter.return_value = []
    with mock.patch.object(AssessmentSession.objects, "select_for_update", return_value=empty):
        with pytest.raises(AssessmentInProgress):
            _start(cand)

    assert list(AssessmentSession.objects.filter(candidate=cand)) == [existing]
    assert not AssessmentItem.objects.filter(assessment__candidate=cand).exists()
