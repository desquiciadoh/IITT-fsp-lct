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
from assessment import cat_bridge
from assessment.models import AssessmentItem, AssessmentSession, LeagueMembership
from assessment.services import (
    DEADLINE_GRACE_S,
    GRADE_ORDER,
    LOWER_GRADE,
    AssessmentService,
)
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
    """A demonstrably wrong answer value for the item's protocol shape.

    Registry families are typed: choice-style items expose `options`
    (pick a non-key option id), numeric/text items expect a literal in
    `value` (submit something other than the key).
    """
    view = item.view or {}
    options = view.get("options") or []
    if options:
        return next(o["id"] for o in options if o["id"] != item.key)
    return f"{item.key}_wrong"


def _answer(client, session, item, value):
    return client.post(
        f"/api/assessments/{session.id}/answers",
        {"item_id": str(item.id), "option_id": value},
        format="json",
    )


def _expire(item, seconds_ago):
    item.deadline_at = timezone.now() - timedelta(seconds=seconds_ago)
    item.save(update_fields=["deadline_at"])


def _serve_next(session):
    """Serve the next engine-selected item (ML-3: one at a time)."""
    item = AssessmentService._serve_next_item(session, timezone.now())
    assert item is not None, "engine stopped before the test window was reached"
    return item


def _time_limit(family_id):
    return cat_bridge.family_meta(family_id).time_limit_s


# --- Bug 1: deadlines are per served item; a late answer never rolls the session back ---


def test_start_sets_deadline_only_for_first_item(cand):
    """ML-3 serve-one-item: start creates exactly ONE item, with a live clock."""
    before = timezone.now()
    session = _start(cand)
    items = _items(session)
    assert len(items) == 1
    first = items[0]

    assert first.deadline_at is not None
    limit = _time_limit(first.family_id)
    assert (
        before + timedelta(seconds=limit)
        <= first.deadline_at
        <= timezone.now() + timedelta(seconds=limit)
    )


def test_next_item_deadline_starts_when_it_is_served(cand, client):
    session = _start(cand)
    first = _items(session)[0]

    before = timezone.now()
    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    body = res.json()
    assert body["done"] is False
    # ML-3: the next item is selected by the engine *after* the answer; its
    # clock starts at that moment (deadline comes from the response, not a
    # pre-seeded row).
    served_before = timezone.now()
    second_id = body["next"]["item_id"]
    assert body["next"]["deadline_at"] is not None
    second = AssessmentItem.objects.get(id=second_id)
    limit = _time_limit(second.family_id)
    assert served_before <= second.deadline_at <= timezone.now() + timedelta(seconds=limit)
    assert second.served_at >= before

    detail = client.get(f"/api/assessments/{session.id}").json()
    assert detail["current"]["item_id"] == str(second.id)
    assert detail["current"]["deadline_at"] is not None
    assert "key" not in detail["current"]


def test_late_answer_is_recorded_wrong_and_test_continues(cand, client):
    session = _start(cand)
    first = _items(session)[0]
    _expire(first, DEADLINE_GRACE_S + 10)

    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    assert res.json()["done"] is False
    second_id = res.json()["next"]["item_id"]
    first.refresh_from_db()
    # The right answer submitted after the deadline is credited (correct=True)
    # but flagged late; the engine scores it incorrect for theta (D1/ML §3).
    assert first.correct is True
    assert first.answer["late"] is True
    session.refresh_from_db()
    assert session.status == AssessmentStatus.IN_PROGRESS

    # Retrying the late item is a normal 409, not a stuck 400.
    retry = _answer(client, session, first, first.key)
    assert retry.status_code == 409
    assert retry.json()["code"] == "item_not_current"
    assert AssessmentItem.objects.get(id=second_id).answered_at is None


def test_answer_within_grace_counts(cand, client):
    session = _start(cand)
    first = _items(session)[0]
    _expire(first, 1)

    res = _answer(client, session, first, first.key)

    assert res.status_code == 200
    first.refresh_from_db()
    assert first.correct is True
    assert first.answer == {"value": first.key}


def test_late_last_item_finalizes_session(cand, client):
    """EAP semantics: all-correct answers -> theta above the Senior cut -> CONFIRMED."""
    session = _start(cand)
    answered = []
    while True:
        current = session.items.filter(answered_at__isnull=True).order_by("seq").first()
        if current is None:
            current = _serve_next(session)
            if current is None:
                break
        answered.append(current)
        # Expire the item BEFORE answering so it is scored late (incorrect);
        # earlier items were all correct -> theta stays above the Senior cut.
        _expire(current, DEADLINE_GRACE_S + 10)
        res = _answer(client, session, current, current.key)
        assert res.status_code == 200
        session.refresh_from_db()
        if res.json()["done"]:
            break

    assert session.status == AssessmentStatus.FINISHED
    assert session.finished_at is not None
    last_item = answered[-1]
    last_item.refresh_from_db()
    # Correct answer submitted late: credited on the row, flagged late; the
    # engine scores it incorrect for theta (D1/ML §3).
    assert last_item.correct is True
    assert last_item.answer["late"] is True
    # All other answers correct -> high theta (EAP) >= Senior cut -> confirmed
    assert session.theta > 1.0
    assert session.decision == GradeDecision.CONFIRMED


# --- Bug 2: instant fallback needs evidence from the same answers; short_test once ---


def _finish_all_wrong(cand, client):
    """Answer every served item wrong; the engine stops at its window -> UNCONFIRMED."""
    session = _start(cand, Grade.SENIOR)
    n = 0
    while True:
        current = session.items.filter(answered_at__isnull=True).order_by("seq").first()
        if current is None:
            current = _serve_next(session)
            if current is None:
                break
        res = _answer(client, session, current, _wrong(current))
        assert res.status_code == 200
        n += 1
        session.refresh_from_db()
        if res.json()["done"]:
            break
    assert n >= 8
    assert session.status == AssessmentStatus.FINISHED
    assert session.decision == GradeDecision.UNCONFIRMED
    return session


def _finish_mixed(cand, client):
    """Half correct / half wrong -> mid-band theta (EAP), still unconfirmed vs Senior."""
    session = _start(cand, Grade.SENIOR)
    i = 0
    while True:
        current = session.items.filter(answered_at__isnull=True).order_by("seq").first()
        if current is None:
            current = _serve_next(session)
            if current is None:
                break
        val = current.key if i % 2 == 0 else _wrong(current)
        res = _answer(client, session, current, val)
        assert res.status_code == 200
        i += 1
        session.refresh_from_db()
        if res.json()["done"]:
            break
    assert session.status == AssessmentStatus.FINISHED
    assert session.decision == GradeDecision.UNCONFIRMED
    return session


def test_instant_fallback_confirms_when_answers_support_lower_grade(cand, client):
    session = _finish_mixed(cand, client)
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    lower_grade = LOWER_GRADE[session.claimed_grade]
    # The replayed theta must support the lower grade for the instant path to exist.
    supported = cat_bridge.grade_of_theta(session.theta)
    if supported is None or GRADE_ORDER.get(supported, 0) < GRADE_ORDER[lower_grade]:
        pytest.skip("engine band below lower grade on this seed; refusal covered elsewhere")

    res = client.post(f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json")

    assert res.status_code == 200
    assert res.json()["result_grade"] == lower_grade
    assert res.json()["decision"] == GradeDecision.CONFIRMED
    lm.refresh_from_db()
    assert lm.grade == lower_grade
    assert lm.status == LeagueStatus.CONFIRMED
    assert lm.next_attempt_at is None


def test_instant_fallback_refused_when_answers_do_not_support_lower_grade(cand, client):
    session = _finish_all_wrong(cand, client)  # theta very low -> below Middle cut
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
    first = _items(session)[0]
    _answer(client, session, first, first.key)
    assert client.post(f"/api/assessments/{session.id}/finish").status_code == 200
    lm = LeagueMembership.objects.get(candidate=cand, specialization=Specialization.BACKEND)
    cooldown = lm.next_attempt_at

    res = client.post(f"/api/assessments/{session.id}/fallback", {"mode": "instant"}, format="json")

    assert res.status_code == 409
    assert res.json()["code"] == "fallback_not_eligible"
    lm.refresh_from_db()
    assert lm.next_attempt_at == cooldown


def test_short_test_fallback_usable_once(cand, client):
    session = _finish_all_wrong(cand, client)

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
