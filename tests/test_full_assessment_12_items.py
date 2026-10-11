"""Verification that Full assessment serves 12 questions and Express serves 6 questions.

Fixes issue where after question 2 the assessment would finalize prematurely because only
2 stub questions were registered in engine_adapter for backend sessions.
"""

import pytest
from assessment.models import AssessmentSession
from core.enums import AssessmentMode, Grade, Specialization, UserRole
from django.utils import timezone
from identity.models import User
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    return User.objects.create_user(
        email="full12_tester@example.com",
        password="password123",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def auth_client(candidate_user):
    c = APIClient()
    c.force_authenticate(user=candidate_user)
    return c


@pytest.mark.django_db
def test_full_assessment_creates_12_items_and_progresses_through_all(candidate_user, auth_client):
    """POST /api/assessments with mode='full' creates 12 items; answering 1..11 continues; item 12 finalizes."""
    res = auth_client.post(
        "/api/assessments",
        {
            "specialization": Specialization.BACKEND,
            "claimed_grade": Grade.MIDDLE,
            "mode": AssessmentMode.FULL,
        },
        format="json",
    )
    assert res.status_code == 201, res.json()
    data = res.json()
    session_id = data["id"]
    assert data["max_items"] == 12

    session = AssessmentSession.objects.get(id=session_id)
    items = list(session.items.order_by("seq"))
    assert len(items) == 12

    # Verify first item has deadline set, remaining items have deadline=None initially
    assert items[0].deadline_at is not None
    for it in items[1:]:
        assert it.deadline_at is None

    # Step through items 1 to 11: none of them should finalize the session
    for seq in range(1, 12):
        item = session.items.get(seq=seq)
        answer_payload = (
            {"item_id": str(item.id), "option_id": item.key}
            if (item.view or {}).get("input") == "choice" or (item.view or {}).get("options")
            else {"item_id": str(item.id), "value": str(item.key)}
        )
        ans_res = auth_client.post(
            f"/api/assessments/{session_id}/answers",
            answer_payload,
            format="json",
        )
        assert ans_res.status_code == 200, ans_res.json()
        ans_data = ans_res.json()
        assert ans_data["done"] is False, f"Question {seq} should NOT finalize the session!"
        assert "next" in ans_data
        assert ans_data["next"]["seq"] == seq + 1
        assert ans_data["next"]["max_items"] == 12

    # Submit 12th (last) question: must finalize session
    last_item = session.items.get(seq=12)
    last_payload = (
        {"item_id": str(last_item.id), "option_id": last_item.key}
        if (last_item.view or {}).get("input") == "choice" or (last_item.view or {}).get("options")
        else {"item_id": str(last_item.id), "value": str(last_item.key)}
    )
    last_res = auth_client.post(
        f"/api/assessments/{session_id}/answers",
        last_payload,
        format="json",
    )
    assert last_res.status_code == 200
    final_data = last_res.json()
    assert final_data["done"] is True, "Question 12 must finalize the session!"
    assert "result" in final_data
    assert final_data["result"]["result_grade"] is not None

    session.refresh_from_db()
    assert session.status == "finished"
    assert session.items.filter(answered_at__isnull=False).count() == 12


@pytest.mark.django_db
def test_express_assessment_creates_6_items_and_finalizes_on_sixth(candidate_user, auth_client):
    """POST /api/assessments with mode='express' creates 6 items; question 6 finalizes."""
    res = auth_client.post(
        "/api/assessments",
        {
            "specialization": Specialization.FRONTEND,
            "claimed_grade": Grade.JUNIOR,
            "mode": AssessmentMode.EXPRESS,
        },
        format="json",
    )
    assert res.status_code == 201
    data = res.json()
    session_id = data["id"]
    assert data["max_items"] == 6

    session = AssessmentSession.objects.get(id=session_id)
    assert session.items.count() == 6

    # Step through items 1 to 5
    for seq in range(1, 6):
        item = session.items.get(seq=seq)
        payload = (
            {"item_id": str(item.id), "option_id": item.key}
            if (item.view or {}).get("input") == "choice" or (item.view or {}).get("options")
            else {"item_id": str(item.id), "value": str(item.key)}
        )
        r = auth_client.post(f"/api/assessments/{session_id}/answers", payload, format="json")
        assert r.status_code == 200
        assert r.json()["done"] is False

    # 6th question finalizes
    item6 = session.items.get(seq=6)
    payload6 = (
        {"item_id": str(item6.id), "option_id": item6.key}
        if (item6.view or {}).get("input") == "choice" or (item6.view or {}).get("options")
        else {"item_id": str(item6.id), "value": str(item6.key)}
    )
    r6 = auth_client.post(f"/api/assessments/{session_id}/answers", payload6, format="json")
    assert r6.status_code == 200
    assert r6.json()["done"] is True
