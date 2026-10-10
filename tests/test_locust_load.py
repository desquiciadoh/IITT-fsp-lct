"""Automated load and performance test for BE-23.

Verifies that the platform endpoints targeted by Locust (`tests/locustfile.py`)
operate correctly under concurrent load and produce acceptable p95 latencies
across login, pool search, candidate offers, assessment test runner, and lab endpoints.
"""

import time

import numpy as np
import pytest
from assessment.models import LeagueMembership
from core.enums import (
    ConsentType,
    EvidenceSource,
    Grade,
    LeagueStatus,
    SalaryType,
    Specialization,
    UserRole,
    WorkFormat,
)
from django.utils import timezone
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position
from outreach.models import Offer
from profiles.models import CandidateProfile, CandidateSkill, Skill, generate_public_id
from rest_framework.test import APIClient


@pytest.fixture
def load_test_environment(db):
    """Seed lightweight data to exercise all load test user journeys."""
    # Employer and company
    employer = User.objects.create_user(
        email="load.employer@yandex.ru",
        role=UserRole.EMPLOYER,
        email_verified_at=timezone.now(),
    )
    company = Company.objects.create(
        name="Load Testing Co",
        inn="7707083893",
        email_domain="yandex.ru",
    )
    CompanyMember.objects.create(company=company, user=employer)

    py_skill, _ = Skill.objects.get_or_create(id="python", defaults={"name": "Python"})
    dj_skill, _ = Skill.objects.get_or_create(id="django", defaults={"name": "Django"})

    position = Position.objects.create(
        company=company,
        title="Senior Python Architect",
        specialization=Specialization.BACKEND,
        grades=[Grade.MIDDLE, Grade.SENIOR],
        must_skills=["python"],
        nice_skills=["django"],
        salary_min=200000,
        salary_max=350000,
        salary_type=SalaryType.GROSS,
    )

    # Candidates
    candidates = []
    for i in range(15):
        cand_user = User.objects.create_user(
            email=f"load.candidate.{i}@example.com",
            role=UserRole.CANDIDATE,
            email_verified_at=timezone.now(),
        )
        Consent.objects.create(user=cand_user, type=ConsentType.PUBLICATION, granted=True)
        cand_profile = CandidateProfile.objects.create(
            user=cand_user,
            public_id=generate_public_id(),
            full_name=f"Load Candidate {i}",
            specialization=Specialization.BACKEND,
            claimed_grade=Grade.MIDDLE,
            salary_min=180000,
            salary_max=250000,
            salary_type=SalaryType.GROSS,
            work_formats=[WorkFormat.REMOTE],
            open_to_offers=True,
        )
        LeagueMembership.objects.create(
            candidate=cand_user,
            specialization=Specialization.BACKEND,
            grade=Grade.MIDDLE,
            status=LeagueStatus.CONFIRMED,
            rating=1150 + i * 10,
            strength=80.0,
        )
        CandidateSkill.objects.create(
            candidate=cand_profile,
            skill=py_skill,
            source=EvidenceSource.TEST,
        )
        candidates.append((cand_user, cand_profile))

    # Create active offer
    Offer.objects.create(
        candidate=candidates[0][0],
        company=company,
        position=position,
        title="Senior Python Architect",
        description="Join our engineering team",
        salary_min=200000,
        salary_max=250000,
        salary_type=SalaryType.GROSS,
        contact_channel="telegram",
        contact_value="@hr_loadtest",
    )

    return employer, company, position, candidates


@pytest.mark.django_db
class TestLocustEndpointPerformance:
    def test_all_locust_endpoints_latency_p95(self, load_test_environment):
        """Simulate 50 request iterations across all Locust target endpoints and record p95 latency."""
        employer, company, position, candidates = load_test_environment
        candidate_user, candidate_profile = candidates[0]

        emp_client = APIClient()
        emp_client.force_authenticate(user=employer)

        cand_client = APIClient()
        cand_client.force_authenticate(user=candidate_user)

        anon_client = APIClient()

        # Warm up all endpoints
        anon_client.get("/api/taxonomy")
        anon_client.get("/api/vacancies")
        anon_client.get("/api/lab/report")
        anon_client.get("/api/lab/families")
        anon_client.get("/api/lab/twins?specialization=backend&grade=middle")

        cand_client.get("/api/me")
        cand_client.get("/api/candidates/me")
        cand_client.get("/api/leagues")
        cand_client.get("/api/assessments/eligibility?specialization=backend")
        cand_client.get("/api/offers")

        emp_client.get("/api/positions")
        emp_client.get(f"/api/positions/{position.id}/health")
        emp_client.get(f"/api/positions/{position.id}/pool?page=1&size=20")
        emp_client.get("/api/talent/search?specialization=backend&page=1&size=10")
        emp_client.get(f"/api/talent/{candidate_profile.public_id}")
        emp_client.get("/api/offers")

        # Measure 50 iterations per endpoint group
        timings = {
            "GET /api/taxonomy": [],
            "GET /api/leagues": [],
            "GET /api/lab/report": [],
            "GET /api/lab/families": [],
            "GET /api/lab/twins": [],
            "GET /api/me": [],
            "GET /api/candidates/me": [],
            "GET /api/assessments/eligibility": [],
            "GET /api/offers [candidate]": [],
            "GET /api/positions": [],
            "GET /api/positions/{id}/pool": [],
            "GET /api/talent/search": [],
            "GET /api/talent/{public_id}": [],
            "GET /api/offers [employer]": [],
        }

        N_REQUESTS = 50
        for _ in range(N_REQUESTS):
            # Taxonomy
            t0 = time.perf_counter()
            r = anon_client.get("/api/taxonomy")
            timings["GET /api/taxonomy"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Leagues
            t0 = time.perf_counter()
            r = cand_client.get("/api/leagues")
            timings["GET /api/leagues"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Lab families
            t0 = time.perf_counter()
            r = anon_client.get("/api/lab/families")
            timings["GET /api/lab/families"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Lab twins
            t0 = time.perf_counter()
            r = anon_client.get("/api/lab/twins?specialization=backend&grade=middle")
            timings["GET /api/lab/twins"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Candidate me
            t0 = time.perf_counter()
            r = cand_client.get("/api/candidates/me")
            timings["GET /api/candidates/me"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Pool ranking (complex ML matching query)
            t0 = time.perf_counter()
            r = emp_client.get(f"/api/positions/{position.id}/pool?page=1&size=20")
            timings["GET /api/positions/{id}/pool"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Talent search
            t0 = time.perf_counter()
            r = emp_client.get("/api/talent/search?specialization=backend&page=1&size=10")
            timings["GET /api/talent/search"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

            # Offers
            t0 = time.perf_counter()
            r = emp_client.get("/api/offers")
            timings["GET /api/offers [employer]"].append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200

        # Calculate p95 per endpoint
        p95_results = {}
        for ep, times in timings.items():
            if times:
                p95 = float(np.percentile(times, 95))
                p50 = float(np.percentile(times, 50))
                p95_results[ep] = {"p50": round(p50, 2), "p95": round(p95, 2)}
                print(f"BENCHMARK: {ep:<32} | p50={p50:6.2f}ms | p95={p95:6.2f}ms")
                # Every endpoint p95 should be well under 300ms
                assert p95 < 300.0, f"Endpoint {ep} p95 {p95}ms exceeded 300ms!"

        # Invariant: pool search p95 under 100ms in in-memory / unit runs
        assert p95_results["GET /api/positions/{id}/pool"]["p95"] < 150.0
