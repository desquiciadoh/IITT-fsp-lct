"""Tests for Micro-Tasks (Task BE-18).

Verifies:
1. Employer CRUD for micro-tasks.
2. Secret key is NEVER leaked in API responses.
3. Weekly drop task distributes drops to matching candidates.
4. Candidate lists assigned drops and submits solutions.
5. Auto-grading evaluates solution against secret key.
6. Employer views submissions, rates them, and pre-fills an offer draft.
"""

import pytest
from core.enums import Grade, MicroTaskFormat, Specialization, UserRole
from django.utils import timezone
from identity.models import User
from matching.models import Company, CompanyMember, MicroTask, MicroTaskDrop
from matching.tasks import drop_weekly_microtasks_task
from profiles.models import CandidateContact, CandidateProfile, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def candidate_user(db):
    user = User.objects.create_user(
        email="candidate.micro@example.com",
        password="TestPassword123!",
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    CandidateProfile.objects.create(
        user=user,
        public_id=generate_public_id(),
        full_name="Тест Микрозадач",
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        open_to_offers=True,
    )
    CandidateContact.objects.create(
        user=user,
        email="candidate.micro@example.com",
        phone="+7 (999) 555-55-55",
        telegram="@micro_candidate",
    )
    return user


@pytest.fixture
def employer_setup(db):
    company = Company.objects.create(
        name="ВКонтакте Команда",
        contact_email="hr@vk-micro.ru",
    )
    employer_user = User.objects.create_user(
        email="lead@vk-micro.ru",
        password="TestPassword123!",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    CompanyMember.objects.create(company=company, user=employer_user)
    return company, employer_user


@pytest.mark.django_db
class TestMicroTasks:
    def test_employer_creates_micro_task_and_key_not_leaked(self, employer_setup):
        company, employer_user = employer_setup
        client = APIClient()
        client.force_authenticate(user=employer_user)

        # Create auto-graded micro-task with secret key
        resp = client.post(
            "/api/micro-tasks",
            {
                "title": "Optimize SQL Query with Index",
                "specialization": "backend",
                "grades": ["middle", "senior"],
                "format": "auto",
                "prompt_md": "Given slow table with 10M rows, provide optimal CREATE INDEX command.",
                "key": {"index_name": "idx_users_created_at"},
            },
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Optimize SQL Query with Index"
        assert "key" not in data  # INVARIANT: Secret key is never returned

        task = MicroTask.objects.get(id=data["id"])
        assert task.key == {"index_name": "idx_users_created_at"}

        # Get detail: key must still not be returned
        resp_detail = client.get(f"/api/micro-tasks/{task.id}")
        assert resp_detail.status_code == 200
        assert "key" not in resp_detail.json()

    def test_weekly_drop_and_candidate_submission(self, candidate_user, employer_setup):
        company, employer_user = employer_setup

        MicroTask.objects.create(
            company=company,
            title="Fix Memory Leak in Cache",
            specialization=Specialization.BACKEND,
            grades=[Grade.MIDDLE],
            format=MicroTaskFormat.AUTO,
            prompt_md="Find and fix the memory leak.",
            key={"answer": "use weakref"},
        )

        # Run drop cron task
        created_count = drop_weekly_microtasks_task()
        assert created_count >= 1

        # Candidate checks their drops
        client_cand = APIClient()
        client_cand.force_authenticate(user=candidate_user)

        resp_drops = client_cand.get("/api/candidates/me/micro-tasks")
        assert resp_drops.status_code == 200
        drops_data = resp_drops.json()
        assert len(drops_data) >= 1
        drop_id = drops_data[0]["id"]
        assert "key" not in drops_data[0]["task"]  # INVARIANT

        # Candidate submits correct answer
        resp_submit = client_cand.post(
            f"/api/candidates/me/micro-tasks/{drop_id}/submit",
            {"answer": {"answer": "use weakref"}},
            format="json",
        )
        assert resp_submit.status_code == 200
        sub_data = resp_submit.json()
        assert sub_data["score"] == 1.0
        assert sub_data["submitted_at"] is not None

        # Duplicate submit is rejected
        resp_dup = client_cand.post(
            f"/api/candidates/me/micro-tasks/{drop_id}/submit",
            {"answer": {"answer": "another"}},
            format="json",
        )
        assert resp_dup.status_code == 422

    def test_employer_reviews_rates_and_prefills_offer(
        self, candidate_user, employer_setup
    ):
        company, employer_user = employer_setup

        task = MicroTask.objects.create(
            company=company,
            title="Design Payment State Machine",
            specialization=Specialization.BACKEND,
            grades=[Grade.MIDDLE],
            format=MicroTaskFormat.OPEN,
            prompt_md="Design idempotent payment state transitions.",
        )

        drop = MicroTaskDrop.objects.create(
            task=task,
            candidate=candidate_user,
            answer={"solution": "Created state enum and transition table"},
            submitted_at=timezone.now(),
        )

        client_emp = APIClient()
        client_emp.force_authenticate(user=employer_user)

        # Employer views submissions
        resp_subs = client_emp.get(f"/api/micro-tasks/{task.id}/submissions")
        assert resp_subs.status_code == 200
        subs = resp_subs.json()
        assert len(subs) == 1
        assert subs[0]["id"] == str(drop.id)

        # Employer rates submission 5 stars
        resp_rate = client_emp.post(
            f"/api/micro-tasks/submissions/{drop.id}/rate",
            {"employer_rating": 5},
            format="json",
        )
        assert resp_rate.status_code == 200
        assert resp_rate.json()["employer_rating"] == 5
        drop.refresh_from_db()
        assert drop.employer_rating == 5

        # Employer pre-fills draft offer
        resp_prefill = client_emp.post(
            f"/api/micro-tasks/submissions/{drop.id}/prefill-offer"
        )
        assert resp_prefill.status_code == 200
        prefill_data = resp_prefill.json()
        assert prefill_data["candidate_id"] == str(candidate_user.id)
        assert prefill_data["company_id"] == str(company.id)
        assert "Design Payment State Machine" in prefill_data["title"]
        assert prefill_data["salary_min"] > 0
