"""Tests for N2: Engine adapter conformance and sync_families management command."""

import random

import pytest
from assessment import engine_adapter
from assessment.models import ItemFamily
from assessment.services import AssessmentService
from core.enums import AssessmentKind, AssessmentMode, Grade, GradeDecision, Specialization
from django.core.management import call_command
from identity.models import User


@pytest.mark.django_db
class TestEngineAdapterContract:
    """Verify ML.md §3 protocol conformance."""

    def test_start_returns_valid_cat_state(self):
        state = engine_adapter.start(
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            mode="full",
            kind="initial",
        )
        assert isinstance(state, engine_adapter.CatState)
        assert state.spec == Specialization.BACKEND
        assert state.claimed == Grade.MIDDLE
        assert state.mode == "full"
        assert state.kind == "initial"
        assert state.administered == []
        assert state.max_items == 15

    def test_cat_state_json_roundtrip(self):
        state = engine_adapter.start(
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            mode="express",
            kind="screening",
        )
        state = engine_adapter.record(
            state,
            family_id="be.sql.group_having.v1",
            correct=True,
            late=False,
        )
        payload = state.to_json()
        assert isinstance(payload, dict)
        assert payload["spec"] == Specialization.BACKEND
        assert len(payload["administered"]) == 1

        restored = engine_adapter.CatState.from_json(payload)
        assert restored.spec == state.spec
        assert restored.claimed == state.claimed
        assert restored.mode == state.mode
        assert restored.theta == state.theta
        assert restored.se == state.se
        assert len(restored.administered) == 1
        assert restored.administered[0]["family_id"] == "be.sql.group_having.v1"

    def test_next_family_and_next_item(self):
        state = engine_adapter.start(
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
        )
        rng = random.Random(42)
        fam = engine_adapter.next_family(state)
        assert fam is not None
        assert fam.spec == Specialization.BACKEND

        item = engine_adapter.next_item(state, rng)
        assert isinstance(item, engine_adapter.Instance)
        assert item.stem_md
        assert item.key is not None

        # Invariant: view() must NEVER expose key or fingerprint
        view_data = item.view()
        assert "key" not in view_data
        assert "fingerprint" not in view_data
        assert "stem_md" in view_data

    def test_record_updates_theta_and_se(self):
        state = engine_adapter.start(
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
        )
        initial_theta = state.theta
        state = engine_adapter.record(state, "be.sql.group_having.v1", correct=True, late=False)
        assert len(state.administered) == 1
        assert state.theta != initial_theta

        # Late submission scores as incorrect
        state = engine_adapter.record(state, "be.algo.complexity.v1", correct=True, late=True)
        assert len(state.administered) == 2
        assert state.administered[1]["correct"] is False
        assert state.administered[1]["late"] is True

    def test_result_produces_cat_result(self):
        state = engine_adapter.start(
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
        )
        state = engine_adapter.record(state, "be.sql.group_having.v1", correct=True)
        state = engine_adapter.record(state, "be.algo.complexity.v1", correct=True)
        res = engine_adapter.result(state)
        assert isinstance(res, engine_adapter.CatResult)
        assert isinstance(res.rating, int)
        assert isinstance(res.rating_ci, int)
        assert res.result_grade in [Grade.INTERN, Grade.JUNIOR, Grade.MIDDLE, Grade.SENIOR]
        assert res.decision in [GradeDecision.CONFIRMED, GradeDecision.UNCONFIRMED]
        assert isinstance(res.evidence, list)

    def test_make_rng_determinism(self):
        rng1 = engine_adapter.make_rng("secret_key", "sess_1", "item", 1)
        rng2 = engine_adapter.make_rng("secret_key", "sess_1", "item", 1)
        assert rng1.randint(1, 100000) == rng2.randint(1, 100000)

        rng3 = engine_adapter.make_rng("secret_key", "sess_1", "item", 2)
        assert rng1.randint(1, 100000) != rng3.randint(1, 100000)


@pytest.mark.django_db
class TestSyncFamiliesManagementCommand:
    """Verify manage.py sync_families populates ItemFamily table idempotently."""

    def test_sync_families_command(self):
        ItemFamily.objects.all().delete()
        assert ItemFamily.objects.count() == 0

        call_command("sync_families")
        assert ItemFamily.objects.count() >= 3

        # Check fields populated correctly
        sql_fam = ItemFamily.objects.get(id="be.sql.group_having.v1")
        assert sql_fam.topic == "sql.aggregation"
        assert Specialization.BACKEND in sql_fam.specs
        assert sql_fam.a == 1.2
        assert sql_fam.b == 0.4

        # Idempotent: running again should not duplicate rows
        call_command("sync_families")
        assert ItemFamily.objects.count() >= 3


@pytest.mark.django_db
class TestAssessmentServiceUsesAdapter:
    """Verify AssessmentService correctly serializes CatState and orchestrates adapter."""

    def test_session_lifecycle_with_adapter(self, db):
        call_command("sync_families")

        user = User.objects.create_user(
            email="candidate_adapter@example.com",
            password="testpassword123",
            role="candidate",
        )

        session = AssessmentService.start_assessment(
            user=user,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            mode=AssessmentMode.FULL,
            kind=AssessmentKind.INITIAL,
        )

        assert session.state is not None
        assert session.state["spec"] == Specialization.BACKEND
        assert session.state["claimed"] == Grade.MIDDLE
        assert session.state["mode"] == "full"

        # First item is initialized and ready to answer
        item = session.items.get(seq=1)
        assert item is not None
        assert "key" not in item.view

        # Submit correct answer
        answered_session, next_item, finished = AssessmentService.submit_answer(
            user=user,
            session_id=session.id,
            item_id=item.id,
            answer_val=item.key,
        )
        assert answered_session.state is not None
        assert len(answered_session.state["administered"]) == 1
        assert answered_session.state["administered"][0]["correct"] is True

        # Finalize assessment
        finalized = AssessmentService.finalize_assessment(answered_session, user)
        assert finalized.theta is not None
        assert finalized.rating is not None
        assert finalized.decision in [GradeDecision.CONFIRMED, GradeDecision.UNCONFIRMED]
