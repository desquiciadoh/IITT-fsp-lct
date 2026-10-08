# FSP Draft: Architecture & Execution Plan

> **Implementation status (2026-10-07):** The current checkout contains the Django 5.x + Django REST Framework backend MVP under `apps/`. The React/FastAPI/Valkey deployment described in the original target architecture is planned work, not shipped code. For implemented behavior, `README.md`, `docs/BACKEND.md`, `requirements.txt`, migrations, and tests are authoritative.

> **Working title.** LCT 2026, FSP track: an IT hiring platform with reverse recruitment and verified achievement profiles.
> **Inputs:** `TK.md` (spec) and `QA.md` (organizer clarifications). **Language:** product UI, deck and jury docs in Russian.

## 0. TL;DR

- **Where the points are.** Matching (35%) and assessment (25%) are 60% of the score. We win those with measured evidence, not feature count. Most of the remaining 40% is cheap: auto-generated OpenAPI, one-command Docker, an SBOM, a rehearsed demo, and concept docs for the bonus items.
- **The product in one line.** A candidate qualifies once through a leak-proof adaptive test and lands in a **League** (specialization × grade). Employers scout ranked, explained pools and send **salary-first Draft Offers**. Contacts unlock only when the candidate accepts.
- **Pitch hook: the sports draft.** Clubs draft players on verified stats; players don't mail in CVs. FSP is a sports federation, so the metaphor lands instantly: League = category, Player Card = profile, Qualification = test, Scouting = talent pool, Draft Offer = invitation, transfer window = grade-change cooldown.
- **Stack.** React + TypeScript SPA, FastAPI modular monolith, PostgreSQL + pgvector, Valkey, CPU-only ML, a domestic LLM (GigaChat) kept off the grading path, and an FSP ID mock that speaks Keycloak-compatible OIDC.
- **One rule we never break: an LLM never decides a grade.** Grades come from IRT scoring over machine-computed answer keys.

---

## 1. Core Value Proposition

### 1.1 The problem
- Employers pay senior engineers to sift through hundreds of keyword-matched, unverified CVs.
- Candidates apply blindly, see the salary late, and rarely hear back.
- FSP holds objective proof of problem-solving skill (placements, sports ranks) that no hiring channel uses today.

### 1.2 Killer features

| # | Feature | What it is | Criterion |
|---|---|---|---|
| 1 | **Leak-proof Qualification** | Every question is an instance of a *parametric item family*. Code, data and names are randomized, and an oracle (Python, Node or SQLite) computes the answer. An adaptive test (CAT) on a calibrated IRT scale gives everyone different questions but comparable grades in 10–15 items, with a confidence interval. | #2 Assessment (25%) |
| 2 | **Explainable Scouting Pools** | Paste a JD → structured hiring need → League shelves → ranked pool. Each candidate shows a score breakdown and reason chips tagged by evidence source (*verified by test*, *verified by FSP*, *declared*), plus counterfactual hints like "drop the Kubernetes must-have → +23 candidates". Filters and weights change live without losing the shortlist. | #1 Matching (35%) |
| 3 | **Salary-first Draft Offers** | An offer card shows the role, RUB from–to (labeled gross or net), the company and a contact channel. Contacts stay gated until acceptance and can be revoked. Both sides see the status change live. Declines carry structured reasons, the candidate sees *why they were picked*, and invitation credits plus a private salary floor stop spam and CV harvesting. | #1 (reverse-flow originality) + #6 (anti-fraud bonus) |

**Force multiplier: the Validation Lab.** `make validate` regenerates every metric (Monte Carlo simulation and a matching benchmark), and the app renders the results. That scores "rigor of self-validation" and "relevance ratio" directly, and turns Q&A answers into "here is the chart".

### 1.3 Scoring map

| Criterion (weight) | What we ship | Proof for the jury |
|---|---|---|
| Novel matching (35%) | Leagues, explainable pools, Draft Offers, credits, two-sided "why", work-sample scouting (P1) | Live two-window demo; nDCG@10 and Precision@10 vs keyword and BM25 baselines; Jury Mode |
| Assessment & validation (25%) | Parametric families, CAT/IRT, grade policy, leak monitor | "Test Twins" view; simulation report (accuracy, retest, leak attack, exposure) |
| UI/UX (10%) | FSP-branded design system, salary-forward offer cards, Player Card PDF | A 4-minute jury route with no dead ends |
| Tech (7%) | Modular monolith, OpenAPI, Docker, SSE, tests, load test | Swagger; p95 latency report |
| Docs (6%) | All 8 mandatory sections, started on day 1; SBOM | `docs/` plus a PDF export |
| Extended (7%) | Vacancies and applications, micro-tasks, anti-fraud, ATS webhook stub, responsive UI | Demo appendix |
| Pitch (10%) | Draft narrative, one evidence slide, Q&A bank | Three timed rehearsals |

---

## 2. Architecture & Tech Stack

### 2.1 Principles
1. **Modular monolith** with strict layers (router → service → repository). Modules talk through service interfaces and in-process domain events, so `assessment` and `matching` can be split out later without a rewrite.
2. **Deterministic core, probabilistic edges.** Grading and ranking are deterministic and reproducible from a seed. LLMs only parse and phrase, always behind a rule-based fallback.
3. **Privacy by construction.** Contacts never leave the API without a grant. Serializers and tests enforce this, not the UI.
4. **CPU-only and offline-capable.** Model weights are baked into the image; the system runs with no LLM keys at all.
5. **Config-driven integrations.** FSP ID is an OIDC issuer URL plus client credentials.

### 2.2 Target system view

```
Browser ─ React SPA: Candidate · Employer · Jury Mode · Validation Lab
   │ HTTPS
Caddy ─── auto-TLS, serves the SPA, proxies /api
   │
API ───── Django + Django REST Framework modular monolith (Swagger at /api/docs)
   │      identity · profiles · assessment · matching · outreach
   │      vacancies · microtasks · fsp · lab
   ├── PostgreSQL 17 + pgvector   system of record, JSONB item params, vectors
   ├── Redis-compatible broker     Celery broker/result backend and future SSE fan-out
   ├── worker (same image, Celery) parsing, embeddings, LLM calls, FSP sync, cron
   ├── LLM gateway                GigaChat → rule-based fallback, PII redacted first
   ├── fsp-id-mock                OIDC on Keycloak-style paths + FSP Registry API
   └── Mailpit                    SMTP sink for email verification (local)
```

### 2.3 Modules

| Module | Owns | Core logic |
|---|---|---|
| identity | users, identities, sessions, consents, audit log | email verification, argon2id, OIDC (BFF), RBAC and ownership guards |
| profiles | profile, skills, contact vault, privacy | PDF parse → prefill; Player Card PDF with a verification QR |
| assessment | item families, attempts, results, cooldowns | generators, CAT/IRT, grade policy, leak monitor |
| matching | leagues, strength, pools, search | scoring, explanations, counterfactuals |
| outreach | positions, offers, credits, contact grants | offer state machine, SSE events, decline analytics |
| vacancies | public vacancies, applications | pipeline statuses (secondary flow) |
| microtasks | employer tasks, drops, submissions | auto-grading, employer review, invite from a submission |
| fsp | FSP links, results, ranks | registry adapter, sync, FSP boost |
| lab | validation report, demo tools | report API, Jury Mode personas, time travel |

### 2.4 Target stack and current implementation

| Layer | Choice | Why | License |
|---|---|---|---|
| Web | React 19 + TypeScript, Vite, Tailwind + shadcn/ui, TanStack Query, React Router, Recharts, Shiki | Planned frontend; no frontend source is present in this checkout | MIT |
| API | Python 3.12, **Django 5.x + Django REST Framework**, drf-spectacular, Django ORM, WSGI | **Current implementation**: modular monolith with session-cookie auth, migrations, RFC 7807 errors and OpenAPI | BSD / MIT |
| Data | PostgreSQL 17 + pgvector | One store for relational data, JSONB and vectors | PostgreSQL |
| Queue / cache | Redis-compatible broker + Celery | **Current implementation**: FSP sync task queue and result backend; Valkey/arq remains a target option | BSD-3 / MIT |
| Auth | Authlib (OIDC client), argon2-cffi, our own `fsp-id-mock` | Swap the mock for real Keycloak through env vars | BSD / MIT |
| Psychometrics | numpy/scipy (in-house CAT/EAP, about 150 LOC), girth (calibration) | Small enough to understand and defend line by line | BSD / MIT |
| NLP | pypdf + pdfplumber, rapidfuzz, sentence-transformers + `deepvk/USER-bge-m3` on CPU | Domestic RU/EN embedding model, ~0.4B params, no GPU | BSD / MIT / Apache-2.0 |
| LLM | GigaChat API (`GigaChat-2` for runtime, `-Pro`/`-Max` for offline drafting) behind a provider-agnostic gateway; YandexGPT adapter optional | Domestic model, no cross-border personal data | Commercial API |
| PDF | WeasyPrint + Jinja2 + qrcode | Standardized Player Card PDF | BSD |
| Edge / ops | Caddy 2, Docker Compose, Mailpit | Auto-HTTPS public link; one command to run | Apache-2.0 / MIT |
| Quality | uv, pnpm, Ruff, pytest, Playwright, Locust, CycloneDX | Reproducible builds; BOM generated automatically | MIT / Apache-2.0 |

Pin exact versions at kickoff (`uv.lock`, `pnpm-lock.yaml`). The BOM deliverable is a CycloneDX SBOM generated in CI (`make sbom`).

**Model usage register** (QA requires every model and use case to be documented):

| Use | Model | Runs in | Fallback |
|---|---|---|---|
| Resume PDF → profile fields | GigaChat-2 | worker, PII redacted | Regex + taxonomy dictionary |
| JD → structured hiring need | GigaChat-2 | worker, cached | Taxonomy keyword extraction |
| "Why this candidate" sentence | GigaChat-2 | worker, facts-only prompt | Template |
| Drafting new item families | GigaChat-2-Pro / Max | offline; no personal data; human review | — |
| Semantic fit, skill alias resolution | USER-bge-m3, local | api / worker | Taxonomy only |
| **Grading** | **None** | — | — |

> GigaChat's free tier for individuals has a large token quota but generates **one stream at a time**. Route every LLM call through the worker queue (concurrency 1 per key), cache results, and fall back to rules on timeout. Since 1 Sep 2026, new clients buy paid packages through cloud.ru. Register on day 1.

### 2.5 Assessment engine ("Qualification")

**An item family** is a template, a generator, an oracle, IRT parameters and skill tags:

```yaml
id: be.sql.group_having.v1
specs: [backend, ml_data]     topics: [sql.aggregation]
format: sql_result            time_limit_s: 120
irt: {a: 1.3, b: 0.4}         # prior from expert standard-setting; recalibrated online
generator: families.sql.group_having:generate   # rng -> stem, code, options, key
oracle: sqlite                # CI recomputes the key independently
```

- **Formats** (QA says no sandbox is needed): `code_output` (Python/JS), `find_bug`, `sql_result` (random tables, SQLite oracle), `complexity`, `numeric_scenario` (capacity, statistics), `concept_mcq` (human-vetted paraphrase and distractor pools).
- **Seed** = HMAC(secret, attempt_id ‖ family_id). Unique per candidate, reproducible for appeals, impossible to guess.
- **CI verification harness:** 1,000 instances per family. It re-checks the key with the oracle and verifies exactly one correct option, distinct options, clean rendering and the size of the variant space. Any failure blocks the merge. Target: zero errors.
- **Authoring:** an LLM drafts families offline, a human reviews, the harness gates. Shared "Algorithms & CS" families count toward every specialization. Target: ≥15 per specialization at checkpoint, ≥40 at final.

**Adaptive test (CAT)**
- 3PL with fixed guessing (c = 1/number of options; 0 for typed answers). θ ~ N(0,1). Cut scores −1 / 0 / +1 separate Intern, Junior, Middle and Senior. They are set by expert standard-setting (bookmark method) and tuned by simulation.
- The first item targets the claimed grade's cut. Scoring uses a neutral N(0,1) prior, so claiming a high grade never inflates the score.
- Each next item maximizes Fisher information at θ̂ within the category's blueprint quotas. It is drawn at random from the top 5 (exposure control) and prefers families the candidate hasn't seen in earlier attempts.
- Stop at ≥10 items once SE ≤ 0.30 or the 95% interval clears the cut; hard cap 20. Express mode (Jury Mode) stops at 8 items, with a wider interval and a visible label.
- Output: θ̂ (EAP) ± SE shown as a sport-style rating (1000 + 200θ), the grade decision, per-topic evidence (strong, moderate or limited), and integrity signals (time per item, focus loss, paste). Integrity signals are shown, never auto-penalized.
- Items are served one at a time with a timer, and answer keys never leave the server.

**Category blueprints vs vacancy tests.** The grade-determining test always uses the fixed category blueprint, which keeps grades comparable. For the TK's "build tests from job descriptions" demo, a JD becomes skills, then topic weights, then a *vacancy screening* blueprint: an optional employer add-on that never changes the grade. Demo: 3 sample JDs → 3 blueprints → unique instances side by side ("Test Twins").

**Grade policy**

| Situation | Rule | Result |
|---|---|---|
| Confirmed | θ̂ ≥ cut(claimed) | `Confirmed <grade>` |
| Decisive | P(θ ≥ next cut) ≥ 0.9 | Confirmed, plus a **promotion test** is unlocked (separate and harder; no automatic jump, as QA prefers) |
| Not confirmed | θ̂ < cut(claimed) | `Unconfirmed <grade>`: stays visible, ranking ×0.75. Free fallback: confirm the highest lower grade with P(θ ≥ cut) ≥ 0.8 from the same answers, or else take a short fallback test. **The attempt is not burned.** |
| Retry at same or higher grade | After a failed claim | 30-day cooldown |
| Promotion | After an upgrade | At most once per 90 days (the "transfer window") |
| Abandoned session | ≥50% of the minimum items answered | Counts as an attempt; at most 2 free restarts per window, which blocks item harvesting |

**Leak resistance in six layers.**
1. Every instance is unique.
2. Answers are instance-specific, so a leaked answer is worthless.
3. Adaptive paths differ per person.
4. A large pool, exposure control, and no repeats on retake.
5. Server-side keys, one item at a time, timers.
6. A **leak monitor** compares each family's observed correct rate with the IRT-expected rate per θ band. Drift auto-flags the family and rotates it out (a "self-healing bank"). Families with discrimination a < 0.6 after calibration are retired.

### 2.6 Matching & ranking

**Leagues.** A category is a specialization × grade pair. The MVP has Backend, Frontend and ML/Data × Intern, Junior, Middle and Senior: 12 leagues. DevOps, QA, Analytics and Mobile are in the directory as roadmap items. Each membership is Confirmed or Unconfirmed (visible but deranked).

**Profile Strength** ranks candidates inside a league (0–100): **0.85 × Base + FSP Boost**.
- Base = 0.75 × θ percentile in the league + 0.15 × verified activity (micro-tasks, 90-day half-life) + 0.10 × profile freshness.
- FSP Boost (0–15) = 12·(1 − e^(−R/2)) + rank bonus. R is the sum of placement weights: winner 1.0, prize-winner 0.7, finalist 0.4, participant 0.15, with participation-only credit capped at 0.6. Placements beat attendance, returns diminish, and all five disciplines weigh the same, as QA asks. Rank bonus: 1st category +1, KMS +2, MS +3.
- No FSP history → boost 0 and a neutral badge, "Verified by platform qualification". Micro-tasks offer an alternative source of evidence. **FSP is a boost, not a gate.**

**Match score** for a hiring need (0–100). Hard filters come first: specialization, allowed grades, work format, location and time zone, open to offers, publication consent, and the candidate's company blocklist.

| Feature | Weight | Definition |
|---|---|---|
| SkillFit | 35 | Σ w·evidence / Σ w, with must-have w = 2 and nice-to-have w = 1. Evidence: verified by test 1.0 (scaled by topic evidence), verified by FSP or micro-task 0.8, declared 0.4, a related skill via the taxonomy 0.5 × its evidence |
| Strength | 20 | Profile Strength, above |
| GradeFit | 15 | Exact and confirmed 1.0; exact and unconfirmed 0.6; adjacent grade (only if allowed) 0.5 |
| SalaryFit | 15 | Overlap between the offer range and the expectation, with gross/net normalized by the NDFL scale |
| SemanticFit | 10 | Cosine similarity of need text and experience text (USER-bge-m3) |
| Freshness | 5 | How recently the candidate was active or did a micro-task |

Weight presets (Balanced, Skills-first, Budget-first) and sliders re-rank live, and the shortlist survives filter changes.

**Explanations are faithful by construction.** The API returns the feature vector, each feature's contribution, reason chips with their evidence source, gaps, and counterfactual relaxations. An optional LLM sentence only rephrases those facts and falls back to a template. The candidate sees the same "why" in the offer, minus employer-internal data.

### 2.7 Draft Offers: the reverse-contact protocol

`SENT → VIEWED → ACCEPTED → INTERVIEW → HIRED / CLOSED`, plus `DECLINED (reason)`, `EXPIRED` (14 days) and `WITHDRAWN` (by the employer, before a response).

- **Mandatory fields**, enforced by DB CHECK constraints and validation: description, company, salary_min ≤ salary_max in RUB, a gross/net label, and a contact channel. A position can stay private (no vacancy needed) or be published as a vacancy, which also requires a salary range.
- **Contact gating:** acceptance or a direct application creates a `contact_grant`, which is audit-logged and revocable by the candidate. Without a grant, contacts are absent from every employer payload.
- **Real time:** every transition emits a domain event, which goes through Valkey pub/sub to both parties over SSE (with 10-second polling as a fallback).
- **Anti-spam and anti-fraud:** N invitation credits per position per week, refunded when an offer is accepted, so precise targeting pays. Candidates can set a private salary floor. Offers below it trigger a "below the candidate's floor" warning for the sender, which is yes/no only and never reveals the value.
- **Feedback loop:** structured decline reasons (salary, stack, format, company, timing, not looking) feed a "Need Health" panel for the employer, e.g. "most declines cite salary".
- **Candidate privacy:** blind mode hides name and photo until acceptance, and a company blocklist can hide the profile from the current employer.
- **Acceptance likelihood (P1):** a heuristic score from the salary ratio, format fit, candidate status and responsiveness, shown as Low, Medium or High next to the Send button.

### 2.8 FSP ID & registry (mocked, Keycloak-ready)

1. "Log in / link FSP ID" starts OIDC Authorization Code + PKCE against `{issuer}/protocol/openid-connect/auth`. It is a backend-for-frontend flow, so tokens never reach the browser.
2. The callback exchanges the code for an `id_token` carrying `sub`, `email` and `fsp_participant_id`.
3. The backend calls the FSP Registry at `GET /participants/{id}/achievements` with a client-credentials token.
4. Results are stored as verified (source, fetched_at, hash) and Profile Strength is recomputed. A periodic job resyncs; in production the registry would push webhooks.
5. Fallbacks: if the registry is down, keep the last snapshot and show "sync pending". No history gets a neutral badge. An FSP ID already linked to another account returns 409 with an explanation.

`fsp-id-mock` serves Keycloak-style paths (`/realms/fsp/...`), discovery, JWKS and synthetic participants. Moving to real Keycloak only changes `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`. A realm export with an `fsp_participant_id` protocol mapper ships in `deploy/keycloak/`. Email/password registration runs alongside, as QA recommends.

Our proposed registry contract:

```json
{ "participant_id": "FSP-000123",
  "sports_rank": { "title": "KMS", "awarded_at": "2025-04-12" },
  "results": [{ "event_id": "…", "event_name": "…", "date": "2025-11-20",
    "discipline": "product", "stage": "final", "format": "team",
    "team": { "name": "…", "size": 4 },
    "placement": 2, "placement_tier": "prize_winner", "participants_total": 120 }],
  "issued_at": "…", "signature": "…" }
```

`discipline` takes one of the five official sports-programming disciplines: `algorithmic`, `product`, `infosec`, `robotics`, `uas`.

### 2.9 Data model (core tables)

- **identity:** `users`, `identities` (local or fsp_id, plus subject), `sessions`, `consents` (type, version, granted/revoked, IP), `audit_log`
- **profiles:** `candidate_profiles` (expectations, formats, privacy JSON, embedding), `candidate_contacts` (separate table, encrypted), `candidate_skills` (source: test, fsp, microtask or declared; level), `skills` (taxonomy, aliases, related)
- **assessment:** `item_families` (IRT a/b/c, status, exposure), `assessments` (kind: initial, fallback, promotion or screening; θ, SE, decision, blueprint), `assessment_items` (seed, rendered item, key hash, response, correct, time), `league_memberships` (spec, grade, status, θ, cooldown_until)
- **fsp:** `fsp_links` (participant, sports rank, sync status), `fsp_results` (discipline, tier, date, team, source hash)
- **employer:** `companies` (INN, domain, trust level), `company_members`, `positions` (private need or public vacancy: must/nice stack, grades, salary, format, weights, embedding), `shortlists`
- **outreach:** `offers` (salary, channel, status, version, match snapshot), `offer_events`, `contact_grants`, `credits`
- **extended:** `applications`, `application_events`, `micro_tasks`, `micro_task_drops` (one row per drop and its submission)

Column-level schema and invariants: `TASKS.md` §1.3.

### 2.10 API surface (current Django MVP)

DRF serves Swagger at `/api/docs` and the generated schema at `/api/schema/`. All implemented paths sit under `/api`; errors use RFC 7807-compatible `problem+json`. Full request/response contracts are in `docs/openapi.json`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `/auth/verify-email`, `/auth/login`, `/auth/logout` · `GET /auth/fsp-id/login?intent=…` (login or link), `/auth/fsp-id/callback` · `GET /me` |
| Candidate | `GET`/`PUT /candidates/me` (profile + privacy) · `PUT /candidates/me/consents` · `POST /candidates/me/resume` (PDF → prefill) · `GET /candidates/me/card.pdf` · `GET /verify/{public_id}` |
| Qualification | `GET /assessments/eligibility` · `POST /assessments` · `GET /assessments/{id}` · `POST /assessments/{id}/answers`, `/finish`, `/fallback` · `GET /assessments/{id}/result` · `GET /assessments` (history) |
| Scouting | `GET`/`PUT /companies/me` · `POST /positions/parse` (JD → structure) · `POST`/`GET /positions` · `GET /leagues` · `GET /positions/{id}/pool` · `PUT`/`DELETE /positions/{id}/shortlist/{public_id}` · `GET /talent/search` (with facets) · `GET /talent/{public_id}` |
| Offers | `POST /offers` · `GET /offers` · `POST /offers/{id}/view`, `/accept`, `/decline`, `/withdraw` · `/revoke-contacts` (P1) · `GET /events` (SSE) |
| Extended | `/vacancies`, `/applications`, `/micro-tasks`, `/webhooks` (ATS) |
| Lab / demo | `GET /lab/report` · `GET /taxonomy` · `POST /demo/persona`, `/demo/reset`, `/demo/time-travel` (DEMO_MODE only) |

### 2.11 Security & 152-FZ

- **RBAC** (candidate, employer, admin) plus ownership checks in the repository layer. A candidate reaches only their own offers and applications, and candidates can't call talent search. Access-control tests run in CI.
- **Credentials and sessions:** argon2id password hashes; HttpOnly, Secure, SameSite session cookies; a CSRF header; rate limits on login, offers and contact reveals; every contact access goes to the audit log.
- **Separate consents:** one for processing, one for publication to employers (art. 10.1, data made available for distribution), one for FSP data sync. Each is versioned and timestamped. Withdrawing consent hides the profile immediately and schedules deletion or anonymization.
- **Localization** (art. 18 part 5): host on a Russian cloud. Use domestic LLMs only, and **redact PII before every call**: name, phone, email and links are extracted locally with regex.
- **P1:** contacts encrypted at rest; exported PDFs watermarked per employer.
- **P2 concept:** minors. An age gate, with a parental-consent flow for ages 15–17.

### 2.12 Validation framework (`make validate`)

**Assessment: Monte Carlo simulation and item QA**
- Simulate 10,000 test-takers with true θ drawn per grade. Responses go through the *real* CAT engine, with item parameters perturbed to mimic imperfect calibration.
- Measure:
  - exact and adjacent grade accuracy, the confusion matrix and weighted κ
  - retest agreement on grade and r(θ̂₁, θ̂₂) across two independent sessions per simulee
  - test information curves, which should peak at the cut scores
  - median test length, maximum family exposure and the instance collision rate
- **Leak attack:** cheaters hold 10%, 30% or 50% of leaked (item, answer) pairs. Compare a static bank against parametric families on θ inflation and the false-promotion rate.
- **Calibration check:** recover a and b with `girth` from simulated responses and report parameter RMSE.
- **Human pilot (P1):** 10–20 volunteers of known seniority, two attempts each.

**Matching: a synthetic world with hidden truth**
- Generate 1,500 candidates and 60 hiring needs from *latent* skills and θ. The matcher sees only noisy observables: declared skills with inflation and omissions, simulated qualification results, FSP history and generated CV text.
- A relevance oracle (0–3) computed from the hidden truth, which the matcher never sees, so the evaluation isn't circular. Two annotators blind-label 300 pairs (Cohen's κ) to validate the oracle.
- Baselines: keyword overlap on declared skills, BM25 on CV text, embeddings only, ours without verified evidence, ours in full.
- Metrics:
  - nDCG@10
  - Precision@10 at relevance ≥ 2 (the "candidate-to-vacancy relevance ratio")
  - Recall@50 and MRR
  - non-FSP exposure parity
  - p95 latency

Targets are in §5.3. Report every number, including the misses: being honest about limits wins Q&A.

### 2.13 Deployment & repo (current checkout)

- The current checkout is started with `python manage.py migrate`, `python manage.py seed --mode=mini`, and `python manage.py runserver`; PostgreSQL is required for the configured runtime database.
- Celery worker/beat commands are documented in `docs/BACKEND.md`. Docker Compose, Caddy, the SPA, Valkey, Mailpit, and a production FSP ID mock are target deployment work, not present runtime components.

```
apps/                 Django apps: identity, profiles, assessment, matching, outreach, fsp_sync, core
config/               Django settings, URLs and Celery configuration
tests/                pytest-django invariant and access-control tests
docs/                 architecture, QA, task plan, backend notes and OpenAPI schema
manage.py             migrate · seed · runserver
```

---

## 3. MVP Scope vs Nice-to-Have

**P0 must be green before anyone touches P1.** P2 items ship as concept and architecture docs (QA allows this for post-MVP items), with stubs at most.

| Area | P0: Must (demo-critical, required by TK/QA) | P1: Should (score multipliers) | P2: Could (concept + stub) |
|---|---|---|---|
| Identity | Email + verification, FSP ID mock login/link, RBAC, sessions | — | Real Keycloak profile, back-channel logout |
| Candidate | Form + PDF prefill, Player Card PDF, consents, privacy, league status, test history, offers inbox | Blind mode, company blocklist, contact revocation | Several specializations per candidate, minors flow |
| Qualification | 3 specializations, ≥15 families each, CAT/IRT, grade policy, cooldowns, fallback, Express mode, JD → blueprint | ≥40 families each, Test Twins, integrity signals, leak monitor, promotion test | Code sandbox, proctoring, anti-plagiarism, FSP-archive challenge tier |
| Matching | Leagues, Strength + FSP boost with fallback, explained pool, faceted search, persistent shortlist | Counterfactuals, weight presets, LLM summary, acceptance likelihood | Learning-to-rank from employer feedback |
| Outreach | Offers with mandatory salary, contact gating, live lifecycle over SSE, accept/decline with reason | Credits, salary floor, Need Health panel | In-platform chat |
| Extended | — | Vacancies and applications, micro-tasks with work-sample scouting, anti-fraud basics (salary sanity, corporate-domain badge, rate limits), responsive layout | ATS webhooks and export, EGRUL company check, employer reputation |
| Evidence | `make validate` report, seed data, Jury Mode with time travel | Validation Lab UI, human pilot, Playwright e2e, Locust load test | — |
| Docs | 8 mandatory sections, OpenAPI, SBOM, runbook, model register | ADRs, polished diagrams | Production roadmap |

---

## 4. Task Distribution

Sizes: **S** ≤ ½ day · **M** 1–2 days · **L** 3+ days.

### 4.1 Phases

| Phase | Window | Exit criterion |
|---|---|---|
| 0. Foundations | Days 1–2 | `docker compose up` shows the login page and Swagger; one item family generates and verifies; OpenAPI stubs let the frontend work against mocks |
| 1. Golden path | → Checkpoint | Candidate: register → qualify → league. Employer: position → pool → offer → accept, live, on a staging URL. Checkpoint concept doc submitted |
| 2. Evidence & differentiators | Checkpoint → final −3 days | Validation report and Lab, polished explanations, vacancies, micro-tasks, anti-fraud basics, complete docs |
| 3. Freeze & rehearse | Last 3 days | Code freeze at T−24 h (commit timestamps are audited), final deploy, video, deck, three rehearsals |

### 4.2 AI / Data: owns the 60%

| Pri | Task | Size |
|---|---|---|
| P0 | Skill taxonomy (~300 skills with aliases and related links); specializations, grades and category blueprints | M |
| P0 | Item-family framework: generator interface, HMAC seeding, renderers, CI verification harness | M |
| P0 | CAT/IRT engine: fixed-c 3PL, EAP, max-information selection with randomesque and content balancing, stopping, grade policy, topic evidence | M |
| P0 | Item-family authoring: everyone writes 2 a day in phase 1; AI/Data reviews | L |
| P0 | Matching scorer: features, weights, explanation payload, Strength and FSP boost | M |
| P0 | Resume/JD parsing: pypdf → PII redaction → LLM with a JSON schema → taxonomy normalization; rule-based fallback | M |
| P0 | Synthetic-world generator (latent truth) feeding both the demo seed and the benchmark | M |
| P0 | Validation suite: assessment simulation, leak attack, matching benchmark → `report.json` and charts | L |
| P1 | USER-bge-m3 embeddings for semantic fit and alias resolution, precomputed at seed time | S |
| P1 | Counterfactual relaxations, acceptance likelihood, grounded LLM summary | M |
| P1 | Leak/drift monitor, girth calibration job, human pilot and annotation (κ) | M |

### 4.3 Backend / API

| Pri | Task | Size |
|---|---|---|
| P0 | Monorepo, compose (7 services), Makefile, CI (lint, tests, harness, SBOM), healthchecks, migrate + seed on boot | M |
| P0 | Identity: register, verify, login, argon2id, cookie sessions, RBAC and ownership guards, access-control tests | M |
| P0 | `fsp-id-mock` (OIDC, JWKS, registry API on Keycloak paths) + Authlib client, account linking, sync job | M |
| P0 | Profiles, consents, privacy, contact vault, Player Card PDF (WeasyPrint + verification QR) | M |
| P0 | Qualification API: attempts, one-item delivery, server-side keys, cooldowns, fallback, Express mode, history | M |
| P0 | Positions and pool/search endpoints (SQL prefilter + scorer, facets, pagination, shortlist) | M |
| P0 | Offer state machine with optimistic locking, contact grants, SSE via Valkey, expiry job, audit log | M |
| P0 | OpenAPI polish (tags, examples, problem+json) → `docs/openapi.json` → frontend client generation | S |
| P0 | Public deploy (Russian VPS, domain, HTTPS) + DEMO_MODE (personas, reset, time travel) | S |
| P1 | Vacancies, applications, pipeline statuses | M |
| P1 | Micro-tasks: CRUD, weekly drops (worker cron), submissions, employer review, invite from a submission | M |
| P1 | Credits, salary sanity rules, corporate-domain badge, rate limits, contact revocation, Need Health aggregates | M |
| P1 | Locust load test at 50 concurrent users + p95 report | S |
| P2 | HMAC-signed ATS webhooks + JSON export; `keycloak` compose profile with realm import | S |

### 4.4 Frontend

UX rules: one primary action per screen; salary and status always visible; verified and declared data always visually distinct; WCAG AA contrast; FSP brand tokens.

| Pri | Task | Size |
|---|---|---|
| P0 | Shell: Vite + React + TS, Tailwind with FSP brand tokens, shadcn/ui, router, TanStack Query, orval client | S |
| P0 | Auth screens + **Jury Mode landing**: a 5-minute evaluation guide, persona buttons (new candidate with or without FSP, employer workspace), reset | M |
| P0 | Onboarding wizard: consent → resume upload with prefill review → specialization survey → claimed grade | M |
| P0 | Test runner (one item, timer, code highlighting, progress) and result screen (league, rating ± CI, evidence chart, fallback/promotion CTA, cooldown) | L |
| P0 | Candidate dashboard: status card, offers inbox (salary-forward cards, "why you", accept/decline with reason, live status), privacy, FSP link, PDF | M |
| P0 | Employer: company profile, position wizard (paste JD → editable chips), League shelves, pool list with score bars and reason chips, candidate drawer, shortlist tray | L |
| P0 | Send Offer modal (salary mandatory, gross/net, channel), live offers board, faceted talent search | M |
| P1 | Validation Lab: confusion matrix, retest scatter, information curves, leak-attack bars, nDCG vs baselines | M |
| P1 | Test Twins and Blueprint Builder views | S |
| P1 | Vacancies, applications and micro-task UIs; responsive layout (the test runner must work on phones); empty and error states | M |
| P1 | Playwright e2e of the golden path | S |

### 4.5 Pitch / Demo / PM

| Pri | Task | Size |
|---|---|---|
| P0 | Docs skeleton on day 1 (8 mandatory sections + model register); collect ADRs and diagrams as the build goes | S |
| P0 | Checkpoint package: repo access, concept doc (testing methodology and matching rationale), progress demo | M |
| P0 | Demo script, personas, 3–5 sample JDs, story data (e.g. "Anna, KMS, prize-winner") | S |
| P0 | Russian UX copy; turn the FSP brand book into design tokens with the frontend | S |
| P1 | Deck (12–14 slides), Q&A bank (20 questions), backup video, three timed rehearsals | M |
| P1 | Mentor sessions to validate the grade taxonomy, achievement schema and 152-FZ approach with FSP experts; log the answers | S |
| P1 | Final package: repo access, deck, deploy link, docs PDF, local-run guide, video | S |
| — | Scope guard: daily 15-minute sync, burn-down against the P0 list, and a firm "no" to P2 creep | — |

---

## 5. Pitch & Demo Strategy

### 5.1 Narrative (6–7 minutes)

1. **Hook (30 s):** "Clubs don't read players' CVs; they draft on verified stats. Why does IT hiring still run on self-written resumes?"
2. **Problem (30 s):** noise for employers; silence and hidden salaries for candidates; FSP's proof of skill goes unused.
3. **Live demo (3 min):** the script below, with two windows side by side.
4. **Evidence (60 s):** one slide with four numbers from the Validation Lab.
5. **Ready for FSP (30 s):** Keycloak in three env vars, the registry contract, 152-FZ, one-command deploy.
6. **Roadmap and business (30 s):** employers pay through subscriptions and offer credits; candidates use it free. Next come anti-fraud, ATS and proctoring.

### 5.2 Demo script: "Jury Express" (about 4 minutes)

1. **Candidate window:** Jury Mode → "Log in with FSP ID" → a synthetic athlete (KMS, prize-winner) → consents → drop in a PDF resume → prefilled profile → Backend, claiming Middle.
2. **Qualification:** answer 2–3 items live to show the adaptive difficulty. Then switch to the same persona you completed just before the pitch, and say so. Result: "Backend · Middle · Confirmed, 1085 ± 60, top 18% of the league" → Player Card PDF.
3. **Employer window:** paste a JD (Middle Python Backend, 250–320k RUB gross) → parsed chips → League shelves → our candidate ranks #3 with reasons (verified SQL, two FSP prizes, 90% salary overlap).
4. **Send a Draft Offer** with the salary filled in. A toast appears live in the candidate window, then the offer card with salary and "why you". Accept. The employer's status flips live and contacts unlock (audit-logged).
5. **Proof:** Test Twins (same JD, two unique tests, the same difficulty profile), then the Validation Lab numbers.
6. **If time allows:** a failed claim → Unconfirmed → free fallback → cooldown → time travel.

**Wow option** (only if rehearsed and the Wi-Fi is solid): judges scan a QR code, take the Express test on their phones, and appear in the employer pool live.

### 5.3 Metrics to show

Targets below. `make validate` measures them; show the real values.

| Metric | Target |
|---|---|
| Generator errors · instance collisions | 0 over ≥1,000 instances per family · ≤0.1% |
| Exact / adjacent grade accuracy (simulation) | ≥80% / ≥98% |
| Retest: same grade · r(θ̂₁, θ̂₂) | ≥80% · ≥0.85 |
| Leak attack: θ inflation, static bank vs ours | Large vs ≈0 (show the bars) |
| Median test length · max family exposure | ≤14 items · ≤0.5 (each exposure is still a unique instance) |
| nDCG@10 · Precision@10 | ≥0.80 · ≥0.80, with a clear lift over the keyword baseline |
| Ablation: verified evidence on vs off | Visible nDCG gain |
| Non-FSP exposure parity | ≥0.8 |
| JD → ranked pool · offer → live update | <5 s · <1 s |
| p95 API latency at 50 concurrent users | <300 ms |
| Contact leaks in access-control tests | 0 |

### 5.4 Edge cases (each one is demoable or covered by a test)

| Case | Behavior |
|---|---|
| No FSP history | Neutral badge, boost 0, alternative evidence through micro-tasks; full functionality |
| FSP registry down | Last snapshot plus "sync pending"; onboarding is never blocked |
| FSP ID already linked to another account | 409 with an explanation; one-to-one mapping enforced |
| Claimed grade not confirmed | Unconfirmed badge, still visible, deranked; free fallback; attempt not burned |
| Abandoned or restarted test | Resumable for 30 minutes; the harvesting limits from §2.5 apply |
| Double submit or back button | Idempotent answer endpoint (item token); no revisiting items |
| Cooldown bypass | Enforced on the server (the UI only mirrors it); time travel exists only in DEMO_MODE |
| Scanned or image-only PDF | Fails gracefully to the manual form with a partial prefill |
| LLM down or rate-limited | Rule-based parsing and template explanations; grading is unaffected |
| Empty pool from strict filters | Counterfactual relaxation suggestions |
| Offer below the candidate's floor | The sender is warned before sending; the candidate sees a "below your floor" tag |
| Concurrent accept and withdraw | State machine with a version column: one action wins, the other gets 409 |
| Unanswered offer | Auto-expires after 14 days; both sides are notified |
| Employer asks for contacts without a grant | Fields are absent from the payload; 403 on the contact endpoint; audit entry |
| Consent withdrawn | Hidden from search immediately; pending offers closed; deletion job scheduled |
| Typo or unknown skill ("Postgress") | Fuzzy and embedding normalization to the taxonomy; unknown skills kept as free tags |
| Gross vs net mismatch | Normalized for scoring; always labeled in the UI |

### 5.5 What to emphasize
- **Evidence over claims:** every number is reproducible with one command, misses included.
- **Objectivity:** no LLM in grading, oracle-verified answer keys, one IRT scale for everyone.
- **Explainability is the scoring itself**, not a post-hoc story, and both sides see it.
- **Trust mechanics:** salary first, contacts on consent, credits against spam.
- **Fair to everyone:** FSP is a bounded boost; strong non-FSP engineers still rise.
- **Ready for production at FSP:** OIDC/Keycloak swap, registry contract, 152-FZ, SBOM, one-command deploy.

### 5.6 Q&A bank (core answers)

| Likely question | Core answer |
|---|---|
| How do you calibrate difficulty without real data? | Expert standard-setting priors, then simulation, then online recalibration (girth) once a family has ~200 responses, with drift monitoring |
| What if a candidate uses ChatGPT during the test? | Per-item timers, integrity signals, adaptive paths, a separate promotion test, and consistency checks against micro-tasks. Proctored "Verified+" is on the roadmap. We don't claim to fully solve unproctored LLM use |
| Why not generate questions with an LLM at runtime? | Error rate and comparability. The LLM drafts offline; oracle-verified generators serve the test |
| Doesn't the FSP boost discriminate? | It is bounded at 15/100 and placement-based, we track a parity metric, and there is an alternative evidence path |
| How do you stop fake employers? | Credits, salary sanity checks, contact gating, trust badges, reputation and an audit log; an EGRUL check is on the roadmap |
| Does it scale? | Stateless API, SQL prefilter with vectorized scoring, a pgvector HNSW index, per-position caching, and modules that can be extracted |
| How do you plug in real FSP ID? | Standard OIDC with three env vars; the realm export and registry contract ship in the repo |

### 5.7 Top risks

| Risk | Mitigation |
|---|---|
| Item content volume | Framework on day 1, everyone authors, LLM drafts, the harness gates |
| LLM quota or outage (freemium is single-stream) | Keys on day 1, worker queue, cached demo JDs, rule-based fallbacks; nothing critical depends on the LLM |
| Demo fragility | Seeded personas, per-judge sandboxes, reset, healthchecks, a backup video, local compose |
| Scope creep | The P0 gate, feature flags, a PM who says no |
| Circular validation | Hidden-truth oracle plus a human-labeled subset; publish the misses |
| OIDC/Keycloak rabbit hole | Own mock on Keycloak paths; real Keycloak only as a P2 profile |
| Ideas leaking early | Keep the repo private until submission (QA notes public repos were indexed); grant jury access at submission |

---

### Sources
- GigaChat API terms for individuals (freemium quota, single-stream generation, cloud.ru billing from 1 Sep 2026): https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs
- `deepvk/USER-bge-m3` model card (Apache-2.0, ~0.4B params, 1024-dim): https://huggingface.co/deepvk/USER-bge-m3
