"""Locust load test suite for FSP Draft (Task BE-23).

Simulates 50 concurrent users exercising core platform journeys:
- Candidate: Persona login, profile, eligibility, adaptive assessment test runner, offers inbox.
- Employer: Persona login, company profile, position management, pool search & ranking, talent card, draft offers.
- Public: Taxonomy, league shelves, vacancies, and lab evaluation endpoints.

Usage:
  locust -f tests/locustfile.py --headless -u 50 -r 10 --run-time 30s --host http://127.0.0.1:8000
"""

import random

from locust import HttpUser, between, tag, task


class BaseFSPUser(HttpUser):
    abstract = True
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.csrf_token = ""
        # Fetch CSRF cookie and token
        res = self.client.get("/api/auth/csrf")
        if res.status_code == 200:
            try:
                self.csrf_token = res.json().get("csrf_token", "")
            except Exception:
                pass
        if not self.csrf_token:
            self.csrf_token = self.client.cookies.get("csrftoken", "")

    def post_with_csrf(self, url, json=None, name=None):
        headers = {}
        if self.csrf_token:
            headers["X-CSRFToken"] = self.csrf_token
        return self.client.post(url, json=json, headers=headers, name=name)


class CandidateUser(BaseFSPUser):
    """Candidate persona: logs in, checks profile, runs test, browses offers."""

    weight = 3

    def on_start(self):
        super().on_start()
        persona = random.choice(["candidate_fsp", "candidate_plain"])
        self.post_with_csrf(
            "/api/demo/persona",
            json={"persona": persona},
            name="/api/demo/persona [candidate]",
        )
        self.active_assessment_id = None

    @task(4)
    @tag("profile")
    def get_me_and_profile(self):
        self.client.get("/api/me", name="/api/me")
        self.client.get("/api/candidates/me", name="/api/candidates/me")

    @task(3)
    @tag("assessment")
    def check_eligibility_and_leagues(self):
        self.client.get(
            "/api/assessments/eligibility?specialization=backend",
            name="/api/assessments/eligibility",
        )
        self.client.get("/api/leagues", name="/api/leagues")

    @task(2)
    @tag("assessment")
    def assessment_lifecycle(self):
        # Start or resume assessment
        res = self.post_with_csrf(
            "/api/assessments",
            json={
                "specialization": "backend",
                "claimed_grade": "middle",
                "mode": "express",
            },
            name="/api/assessments [start]",
        )
        if res.status_code == 201:
            data = res.json()
            session_id = data.get("id")
            if session_id:
                self.client.get(f"/api/assessments/{session_id}", name="/api/assessments/{id} [detail]")
                # Submit answer
                self.post_with_csrf(
                    f"/api/assessments/{session_id}/answers",
                    json={"answer": {"choice": "1"}},
                    name="/api/assessments/{id}/answers [submit]",
                )
                # Finish assessment
                self.post_with_csrf(
                    f"/api/assessments/{session_id}/finish",
                    json={},
                    name="/api/assessments/{id}/finish",
                )
                # Get result
                self.client.get(
                    f"/api/assessments/{session_id}/result",
                    name="/api/assessments/{id}/result",
                )

    @task(3)
    @tag("outreach")
    def check_offers_and_applications(self):
        self.client.get("/api/offers", name="/api/offers [candidate]")
        self.client.get(
            "/api/candidates/me/applications",
            name="/api/candidates/me/applications",
        )


class EmployerUser(BaseFSPUser):
    """Employer persona: manages vacancies, searches candidate pools, issues draft offers."""

    weight = 2

    def on_start(self):
        super().on_start()
        self.post_with_csrf(
            "/api/demo/persona",
            json={"persona": "employer"},
            name="/api/demo/persona [employer]",
        )
        self.position_ids = []
        # Pre-fetch existing positions
        res = self.client.get("/api/positions", name="/api/positions [setup]")
        if res.status_code == 200:
            try:
                data = res.json()
                items = data.get("items", data) if isinstance(data, dict) else data
                if isinstance(items, list):
                    self.position_ids = [p["id"] for p in items if "id" in p]
            except Exception:
                pass

    @task(3)
    @tag("matching")
    def view_positions_and_health(self):
        res = self.client.get("/api/positions", name="/api/positions")
        if res.status_code == 200 and self.position_ids:
            pos_id = random.choice(self.position_ids)
            self.client.get(f"/api/positions/{pos_id}/health", name="/api/positions/{id}/health")

    @task(4)
    @tag("matching")
    def search_pool(self):
        if self.position_ids:
            pos_id = random.choice(self.position_ids)
            self.client.get(
                f"/api/positions/{pos_id}/pool?page=1&size=20",
                name="/api/positions/{id}/pool",
            )
        else:
            self.client.get(
                "/api/talent/search?specialization=backend&grades=middle&page=1&size=20",
                name="/api/talent/search",
            )

    @task(2)
    @tag("matching")
    def search_talent_and_view(self):
        res = self.client.get(
            "/api/talent/search?specialization=backend&page=1&size=10",
            name="/api/talent/search",
        )
        if res.status_code == 200:
            try:
                items = res.json().get("items", [])
                if items:
                    public_id = items[0].get("public_id")
                    if public_id:
                        self.client.get(f"/api/talent/{public_id}", name="/api/talent/{public_id}")
            except Exception:
                pass

    @task(3)
    @tag("outreach")
    def manage_offers(self):
        self.client.get("/api/offers", name="/api/offers [employer]")


class PublicUser(BaseFSPUser):
    """Anonymous visitors: taxonomy, public vacancies, leagues, and lab diagnostics."""

    weight = 1

    @task(3)
    def view_public_data(self):
        self.client.get("/api/taxonomy", name="/api/taxonomy")
        self.client.get("/api/vacancies", name="/api/vacancies")

    @task(2)
    def view_lab_endpoints(self):
        self.client.get("/api/lab/report", name="/api/lab/report")
        self.client.get("/api/lab/families", name="/api/lab/families")
        self.client.get(
            "/api/lab/twins?specialization=backend&grade=middle",
            name="/api/lab/twins",
        )
