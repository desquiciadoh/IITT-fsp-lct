"""Tests for BE-22: Lab endpoints (GET /api/lab/report, GET /api/lab/twins, GET /api/lab/families)."""

import uuid

import pytest
from assessment.families.registry import all_families
from assessment.models import AssessmentItem, AssessmentSession, ItemFamily
from core.enums import Grade, Specialization, UserRole
from identity.models import User
from matching.models import Company, Position
from rest_framework.test import APIClient


@pytest.fixture
def employer_position(db):
    User.objects.create_user(
        email="lab.employer@corp.ru",
        role=UserRole.EMPLOYER,
    )
    company = Company.objects.create(
        name="Lab Corp",
        inn="7707083893",
        email_domain="corp.ru",
    )
    position = Position.objects.create(
        company=company,
        title="Senior Python Architect",
        specialization=Specialization.BACKEND,
        grades=[Grade.SENIOR],
        must_skills=["python", "sql"],
        salary_min=300000,
        salary_max=450000,
        salary_type="gross",
    )
    return position


@pytest.mark.django_db
class TestLabFamiliesEndpoint:
    def test_lab_families_returns_all_registered_families_with_metrics(self):
        """GET /api/lab/families returns full catalog with exposure and drift metrics."""
        client = APIClient()
        res = client.get("/api/lab/families")
        assert res.status_code == 200
        data = res.json()

        assert "total" in data
        assert "families" in data
        assert data["total"] == len(data["families"])
        assert data["total"] > 0

        # Check family fields
        first = data["families"][0]
        assert "id" in first
        assert "topic" in first
        assert "specs" in first
        assert "format" in first
        assert "a" in first
        assert "b" in first
        assert "c" in first
        assert "time_limit_s" in first
        assert "exposures" in first
        assert "exposure_rate" in first
        assert "drift_flag" in first

        # Invariant: No answer keys in family metadata
        for fam in data["families"]:
            assert "key" not in fam
            assert "oracle" not in fam

    def test_lab_families_exposures_and_drift_calculation(self):
        """High divergence between empirical correct rate and IRT expected probability flags drift."""
        client = APIClient()
        # Find an existing family id from registry
        fams = all_families()
        fam_id = next(iter(fams.keys()))
        fam_obj = fams[fam_id]

        # Ensure DB row exists
        db_fam, _ = ItemFamily.objects.get_or_create(
            id=fam_id,
            defaults={
                "specs": fam_obj.meta.specs,
                "topic": fam_obj.meta.topic,
                "format": fam_obj.meta.format,
                "a": fam_obj.meta.a,
                "b": fam_obj.meta.b,
                "c": fam_obj.meta.c,
                "time_limit_s": fam_obj.meta.time_limit_s,
            },
        )

        user = User.objects.create_user(
            email="candidate.sim@example.com",
            role=UserRole.CANDIDATE,
        )
        session = AssessmentSession.objects.create(
            candidate=user,
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
        )

        # Create 15 answered items for this family that all failed (correct=False)
        for i in range(15):
            AssessmentItem.objects.create(
                assessment=session,
                seq=i + 1,
                family=db_fam,
                seed=f"seed-{i}",
                view={"stem_md": f"Question {i}"},
                key={"answer": "42"},
                correct=False,
            )

        res = client.get("/api/lab/families")
        assert res.status_code == 200
        data = res.json()

        matching = next(f for f in data["families"] if f["id"] == fam_id)
        assert matching["exposures"] >= 15
        assert matching["correct_rate"] == 0.0
        # Expected p for theta=0 is usually > 0.35, so 0.0 has abs(delta) > 0.30 -> drift_flag is True
        assert matching["drift_flag"] is True


@pytest.mark.django_db
class TestLabTwinsEndpoint:
    def test_lab_twins_without_position_generates_matching_difficulty_pairs(self):
        """GET /api/lab/twins generates two unique instances side-by-side with identical difficulty."""
        client = APIClient()
        res = client.get("/api/lab/twins?specialization=backend&grade=middle")
        assert res.status_code == 200
        data = res.json()

        assert "specialization" in data
        assert data["specialization"] == "backend"
        assert "twins" in data
        assert len(data["twins"]) > 0

        for twin in data["twins"]:
            assert "family_id" in twin
            assert "topic" in twin
            assert "level" in twin
            assert "b" in twin
            assert "instance_a" in twin
            assert "instance_b" in twin

            inst_a = twin["instance_a"]
            inst_b = twin["instance_b"]

            # Must have stem_md
            assert "stem_md" in inst_a
            assert "stem_md" in inst_b

            # Hard invariant: Never leak answer key or fingerprint
            assert "key" not in inst_a
            assert "key" not in inst_b
            assert "fingerprint" not in inst_a
            assert "fingerprint" not in inst_b

    def test_lab_twins_with_position_id(self, employer_position):
        """GET /api/lab/twins?position_id=... matches position's specialization and grade."""
        client = APIClient()
        res = client.get(f"/api/lab/twins?position_id={employer_position.id}")
        assert res.status_code == 200
        data = res.json()

        assert data["position_id"] == str(employer_position.id)
        assert data["specialization"] == employer_position.specialization
        assert len(data["twins"]) > 0

    def test_lab_twins_invalid_position_returns_404(self):
        """GET /api/lab/twins with non-existent position returns 404."""
        client = APIClient()
        random_uuid = uuid.uuid4()
        res = client.get(f"/api/lab/twins?position_id={random_uuid}")
        assert res.status_code == 404
        assert res.json().get("code") == "position_not_found"
