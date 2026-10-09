# BE.md: Backend Tasks (owner: BIKHE)

> **Audience:** the backend developer (BIKHE) and their AI coding agent.
> **Scope:** all backend work that is **not** AI/ML: Django/DRF, data model, security, offers, consents, FSP linking, demo mode, deployment, CI, API contract for the frontend, and the *wiring* of ML/LLM modules.
> **Source:** an audit of merge `3cf4044` (PR #1, `bikhe/feature/backend-mvp-p0`), plus the remaining backend tasks from `docs/TASKS.md`.
> **Stack decision:** stay on Django 5.x + DRF. Don't migrate to FastAPI.
> **Date:** 2026-10-08.
> **Start here (2026-10-09):** §9 has the status after the PR #2 review: what the hotfix fixed, the rework list (R1–R26) and the remaining tasks with how to do them.

---

## 0. Team, Ownership and Related Files

| File | Owner | Scope |
|---|---|---|
| **BE.md** (this file) | BIKHE, backend | Django apps, models and migrations, views and serializers, permissions, settings, Celery wiring, OIDC mock, seed loading, deployment, CI, OpenAPI |
| [ML.md](ML.md) | ML engineer | Item families, CAT/IRT engine, grading math, matching scorer, Profile Strength and FSP boost formulas, percentiles, embeddings, synthetic world, validation suite |
| [AI.md](AI.md) | AI / LLM API engineer | LLM gateway (GigaChat + fake), resume and JD parsing, PII redaction, skill taxonomy and `normalize_skill`, grounded "why" sentences, LLM-assisted item drafting |
| [FE1.md](FE1.md) | Frontend dev 1 | Web scaffold, design system, auth/shell, Jury Mode, candidate side |
| [FE2.md](FE2.md) | Frontend dev 2 | Test runner, employer side (positions, scouting, offers board, talent search), Lab |

**Boundary rules**

1. **ML and AI code is pure.** It has no ORM, no views and no request objects. It lives in its own packages: `apps/assessment/engine/`, `apps/assessment/families/`, `apps/matching/engine/`, `apps/llm_gateway/` and `apps/taxonomy/`. **You** own everything that calls it: views, services, Celery tasks, persistence, endpoints. Don't edit the formulas. Do edit the adapters.
2. **ML owns the engine signatures** ([ML.md §3](ML.md)). **AI owns the gateway signatures** ([AI.md §3](AI.md)). A signature change is one PR that touches both sides.
3. **The frontend codes against the generated OpenAPI schema.** Every API change you make must regenerate `docs/openapi.json` (real JSON; see P0) in the same PR. §2.3 lists the contract gaps the frontend is waiting on.
4. **Reassigned to you:** `fsp-id-mock` (TASKS AI-08) is integration plumbing, not AI/ML, so it now belongs to backend. The FSP registry *data* comes from ML's synthetic world (AI-09).

---

## 1. Executive Summary

**Verdict: integrated structurally, but not demo-ready or production-ready.**

The merge sets up a sensible Django modular monolith. It has seven apps. It has DB-level salary `CheckConstraint`s, a separate `candidate_contacts` table and a `ContactAccessService` gate. `OfferService.transition()` uses `select_for_update` and a version check correctly. The serializer keeps the answer key out of responses. It has an RFC 7807 error handler. `manage.py check` passes. `makemigrations --check` reports no drift. The committed OpenAPI matches the routes.

Behind that, these backend problems block the demo or are security issues (details in §4):

- **The app cannot start as documented.** `config/wsgi.py` does not exist, so `runserver` fails **[verified]**.
- **Tenant isolation is broken.** Employers without a company are auto-joined to a company found *by name*.
- **Privileges can be escalated.** Anyone can self-register as `admin` **[verified]**. The demo persona endpoint (on by default) logs into any `<anything>@example.com` account.
- **Privacy and 152-FZ are violated.** Revoked publication consent doesn't remove a candidate from the pool or search. The talent card has no visibility check.
- **Server-side PDF rendering has an SSRF / local-file-read risk.** WeasyPrint renders unescaped user HTML.
- **FSP integrity fails.** Anyone can claim any FSP ID. Each sync *adds* the FSP boost again.
- **The assessment session lifecycle is broken.** Deadlines aren't enforced, a stuck session blocks the candidate forever, and nothing is atomic. The grading math itself moves to ML (see ML.md).
- **SSE returns 406 to browsers** **[verified]**.
- **Bad salaries crash.** Salary validation can be bypassed, which leads to a 500 **[verified]**.
- **Docs and `TASKS.md` claim work that doesn't exist.**

**Method:** read all of `apps/`, `config/`, `tests/` and the docs. Ran `manage.py check`, `check --deploy`, `makemigrations --check`, `spectacular` and `ruff`, plus a script that reproduces the DB-independent bugs (marked **[verified]**). `pytest` was **not** run: the local Postgres credentials were unavailable. The claim "18/18 passing" is unconfirmed.

---

## 2. Hand-offs and Contracts

### 2.1 ML boundary (see [ML.md](ML.md))

| Concern | ML delivers (pure) | You deliver (Django) |
|---|---|---|
| Item families | `apps/assessment/families/` registry and `make_rng()` (HMAC seed) | Sync `FamilyMeta` → `ItemFamily` rows (data migration or `manage.py sync_families`). Stop creating rows lazily in the view (`assessment/views.py:137-148`) |
| CAT/IRT | `CatEngine.start / next_family / record / result`; `CatState.to_json() / from_json()` | `assessment/services.py`: persist `CatState` in `AssessmentSession.state`; serve one item at a time; enforce deadlines (`late=True` → `record(..., correct=False)`); finish, abandon and fallback endpoints; cooldowns; league update |
| Matching | `score_pool(need, pool, weights) -> list[Scored]`, `CandidateCtx` and `NeedCtx` DTOs | SQL prefilter (visibility and hard filters), one batched ORM load → DTOs, pagination, facets, `PoolItem` serialization |
| Strength / FSP boost / percentiles | `strength()`, `fsp_boost()`, `percentiles()` | Store `base_strength` and `fsp_boost` separately on `LeagueMembership` (migration). A `recompute_league(spec, grade)` service, triggered after finalize and after FSP sync. Must be idempotent |
| Synthetic world | `seed_data/full/*.jsonl` plus a schema README; FSP registry data | `manage.py seed --mode=full` loader (BE-13); `fsp-id-mock` serves the registry data |
| Validation report | `validation/out/report.json` and `report.fixture.json` | `GET /api/lab/report` (BE-22) |

**Until ML ships:** keep the current `engine.py` behind a thin adapter so the API shape doesn't change when the real engine lands. Put the stub logic **in the adapter**, not in views.

### 2.2 AI / LLM boundary (see [AI.md](AI.md))

| Concern | AI delivers | You deliver |
|---|---|---|
| Resume parse | `llm_gateway.parse_resume(pdf_bytes) -> ResumeParseResult` (sync, with built-in fallback to rules) | `POST /api/candidates/me/resume`: size limit (≤5 MB), MIME check, a Celery task on queue `llm` (worker `--concurrency=1`), wait ≤15 s and then return the rules result, error `unreadable_pdf` |
| JD parse | `llm_gateway.parse_jd(text) -> JdParseResult` | `POST /api/positions/parse` (employer-only, throttled), same queue pattern |
| Taxonomy | `content/skills.yaml` and `taxonomy.normalize_skill(raw)` | `manage.py sync_taxonomy` (YAML → `Skill` rows); profile update maps skills through `normalize_skill` and **never** creates `Skill` rows from user input (B23) |
| "Why" sentence (P1) | `llm_gateway.phrase(facts) -> str` (template fallback) | Call it when creating an offer and store it next to `why_you` |
| Settings | Reads `LLM_PROVIDER`, `GIGACHAT_*` | Add the env vars to settings and `.env.example`; configure `CACHES` (Redis) for the gateway cache |

### 2.3 Frontend contract gaps (FE1 and FE2 are blocked or mocking these)

The frontend generates its client from the OpenAPI schema. Until an item below ships, they mock it with MSW. Add each one with a request/response serializer, `@extend_schema` and error codes, and regenerate the schema.

| # | Gap | Needed by |
|---|---|---|
| G1 | `GET /api/auth/csrf` (`ensure_csrf_cookie`, 204); `CSRF_TRUSTED_ORIGINS` from env (incl. `http://localhost:5173`). The CSRF header is Django's `X-CSRFToken`, not `X-Requested-With` as `TASKS.md` §1.4 says. Update the docs | FE1 (client) |
| G2 | `POST /api/auth/verify-email {token}` → 204 (`django.core.signing`); `register` returns `verify_link` in DEMO_MODE | FE1 |
| G3 | `GET /api/taxonomy` → specializations (+topics), grades (+descriptor, rating cut, from ML's `content/grades.yaml`), skills (from AI's `skills.yaml`), decline reasons | FE1, FE2 |
| G4 | `POST /api/demo/reset` (DEMO_MODE): resets the caller's persona data and clock offset | FE1 (Jury Mode) |
| G5 | Assessment: `POST /assessments/{id}/finish`, `POST /assessments/{id}/fallback {mode}`. ItemView gains `max_items`, `level`, `format`. AssessmentResult gains `rating_ci`, `topics[]`, `evidence[]`, `next_attempt_at`, `fallback` (values come from ML's `CatResult`) | FE2 (runner), FE1 (result) |
| G6 | `POST /api/positions/parse {text}` → `JdParseResult` | FE2 |
| G7 | `GET /api/leagues?specialization=` → `LeagueShelf[]` (confirmed and unconfirmed counts per grade, median expectation) | FE2 |
| G8 | Pool and search take query params `grades, skills, fsp, formats, salary_max, confirmed_only, preset, page, size`. Response: `{items, total, page, pages, facets, relaxations: []}`; `PoolItem.components` becomes a **list** `{key, value, weight, contribution}`; `gaps[]` | FE2 |
| G9 | TalentShort gains `display_name` (alias in blind mode) and `verified_topics[]`. TalentCard gains `topics`, `fsp_results`, `assessments`, `integrity_flags` | FE2 |
| G10 | Employer offer view includes `talent: TalentShort`; decline exposed as `decline: {reason, comment}` | FE2 |
| G11 | `GET /api/lab/report` serves `validation/out/report.json`, or the fixture with `synthetic_fixture: true` | FE2 |
| G12 | Working SSE (B14) with events `offer.created`, `offer.updated`, `league.updated`, `fsp.synced` (payloads per TASKS §1.4) | FE1, FE2 |
| G13 | One error shape: `errors: [{field, msg}]` (B18) | FE1, FE2 |
| G14 | Consistent pagination `{items, total, page, pages}` on `GET /offers`, `GET /assessments`, `GET /talent/search` | FE1, FE2 |
| G15 | OIDC: `GET /api/auth/fsp-id/login?intent=login\|link`, `GET /api/auth/fsp-id/callback` | FE1 |
| G16 | `GET /api/positions/{id}/shortlist` → `TalentShort[]`, so the shortlist tray survives filters and pagination | FE2 |
| G17 | `POST /api/companies` (an employer creates their company; this replaces the B1 auto-create) and `GET /api/companies?search=` (minimal `{id, name}` for the candidate blocklist picker) | FE2, FE1 |

**Salary shape decision (proposed):** keep the **flat** fields `salary_min`, `salary_max` and `salary_type` that the code already uses. Retire the nested `Salary` object from `TASKS.md` §1.4 to avoid churn, and update §1.4 once FE agrees.

### 2.4 Tasks moved to you

- **AI-08 `fsp-id-mock`.** OIDC discovery, an auth page that picks a synthetic participant, RS256 tokens carrying `fsp_participant_id`, JWKS, userinfo, and `/registry/v1/participants/{id}/achievements` with client credentials. Separate public and internal issuer URLs (TASKS §1.2 "OIDC gotcha"). It can be a small Django app (`apps/fsp_mock/`) mounted under `/idp/` in DEMO_MODE, or a tiny separate service. Your choice; document it.
- **F-02** compose, Makefile and `.env.example`. **BE-15** staging and CD.

---

## 3. Architectural & Code Deviations (backend)

**A1. No service layer.** ARCHITECTURE §2.1 requires "router → service → repository". Only `outreach` has a `services.py`. Domain logic sits in `APIView` methods:
- `apps/assessment/views.py:96-169` and `:238-296` (start, finalize, league update).
- `apps/fsp_sync/views.py:63-111` (`sync_candidate_fsp_data`; `fsp_sync/tasks.py:5` and a test import it from `views`).
- `apps/matching/views.py:115-154` (pool building).
- `matching/views.py:16-28` (`get_employer_company` is imported across apps from a views module).

**A2. Inverted dependency.** `apps/core/services.py:18-21` imports `identity`, `outreach` and `profiles` models, so `core` is not a leaf. `outreach.services → core.services → outreach.models` forms a cycle.

**A3. Module map differs from ARCHITECTURE §2.3, and the differences are undocumented.** Leagues and Strength live in `assessment`. Positions live in `matching`. FSP is `fsp_sync` with an in-code `MOCK_REGISTRY`. The `Identity` model is never used, and FSP linking bypasses it. Either update the doc or move the code. Updating the doc is cheaper.

**A4. No domain events.** `league.updated`, `fsp.synced` and `offer.updated` are never emitted, and percentiles are never computed. You own the event bus (Redis pub/sub → SSE) and the recompute triggers. ML owns the percentile formula.

**A5. Assessment engine integration.** The math is ML-owned (ML.md). On your side:
- Views call `FAMILIES_REGISTRY` and `score_assessment` directly.
- Family selection is hardcoded `families[:3]` (`views.py:122-131`).
- The seed is `sha256(...)`, not HMAC (`:132-133`).
- `ItemFamily` rows are created lazily, with the invalid `format='choice'` (`:137-148`).

Replace all of this with a call into ML's `CatEngine` behind `assessment/services.py`.

**A6. Matching integration.** The formula is ML-owned. On your side:
- No SQL hard filters (specialization, grades, adjacency, work format).
- The scorer receives ORM objects and lazily queries them (N+1).
- `Position.weights` is never passed to the scorer.

Build `CandidateCtx` and `NeedCtx` DTOs from one batched query.

**A7. Outreach protocol is incomplete (ARCHITECTURE §2.7).**
- No expiry job, and `transition()` ignores `expires_at`.
- No `interview`, `hired` or `close` endpoints.
- `why_you` is client-supplied, and `match_snapshot` is never written.
- No credits, no salary floor warning, no email-verified reachability check.

**A8. FSP ID has no OIDC (ARCHITECTURE §2.8).** `authlib` is listed in requirements but never imported. Linking is a bare `POST {participant_id}`.

**A9. `sys.path` hack.** `config/settings.py:6` puts `apps/` on `sys.path`, so apps import as top-level `core`, `identity` and so on. Prefer `apps.<name>` with `AppConfig.name='apps.identity'` and `label='identity'`; migrations stay valid. **Coordinate with ML and AI before switching**: their packages under `apps/` change import paths too. Until then, avoid new top-level names that clash with PyPI packages (that's why the LLM package is `llm_gateway`, not `llm`).

**A10. Settings are not environment-aware.** One `settings.py` with insecure defaults (B8). No `LOGGING`, `CACHES` or `CSRF_TRUSTED_ORIGINS`. `python-dotenv` is installed but `load_dotenv()` is never called. No `.env.example`, even though TASKS §1.2 defines the contract.

**A11. Celery is wired only partially.** `config/__init__.py` doesn't import the Celery app. `django-celery-beat` is installed but missing from `INSTALLED_APPS`. There's no `CELERY_BEAT_SCHEDULE`, so `celery beat` schedules nothing. There's no `llm` queue.

**A12. pgvector.** It is claimed but unused. The ML embeddings task (P1) needs from you: a migration with `CREATE EXTENSION vector`, `VectorField(1024)` on profiles and positions, and an HNSW index.

**A13. Frontend location.** `TASKS.md` §1.1 places the SPA in `apps/web`, but `apps/` is now the Django package root and is on `sys.path`. **Decision: the SPA lives in `web/` at repo root** (FE1 scaffolds it). Update `TASKS.md`, `ARCHITECTURE.md` and the CI paths to match.

---

## 4. Critical Bugs & Flaws (backend)

Severity: 🔴 critical · 🟠 high · 🟡 medium. IDs are stable; ML.md and the FE files cross-reference them.

### Security & privacy

**B1 🔴 Cross-tenant company merge.**
`apps/matching/views.py:16-28` attaches an employer without a membership to `Company.objects.get_or_create(name=f"Компания {local_part}")`. So `ivan@acme.ru` and `ivan@evil.com` share one company, including its positions, offers and unlocked contacts. This is not gated by `DEMO_MODE`. Candidates calling `POST /offers/{id}/withdraw` (`outreach/views.py:194`) and admins listing offers (`outreach/views.py:36`) also get companies created for them.

**B2 🔴 Anyone can self-register as admin.**
`apps/identity/views.py:23` accepts `role=admin` **[verified]**.

**B3 🔴 Demo persona works as an impersonation backdoor.**
`apps/identity/views.py:181-200` with `DEMO_MODE` defaulting to on (`config/settings.py:11`). The free-text `persona` logs in as any existing `X@example.com` with no `is_demo` check. Otherwise it creates the account with the fixed password `demopassword`.

**B4 🔴 Revoked consent is ignored (152-FZ).**
`apps/matching/views.py:122-127` and `:200-205` match *any historical* `granted=True` consent row, so a candidate who revoked publication stays visible. `OfferService.create_offer` (`outreach/services.py:144-150`) does this correctly with the latest row.

**B5 🔴 The talent card has no visibility gate, and denied reads are not audited.**
`apps/matching/views.py:232-255` serves any candidate's card, including `about` and `experience_text` (free text that often contains PII), regardless of consent, blocklist or `open_to_offers`. It checks `has_active_grant()` *before* calling `get_contacts()`, so denied attempts are never audit-logged.

**B6 🔴 WeasyPrint SSRF / local file disclosure.**
`apps/profiles/pdf_service.py:45-201` builds HTML with f-strings and no escaping. `full_name` (`:191`) and skill names (`:184`, user-controlled via `PUT /candidates/me`) are injected. The default `url_fetcher` follows `http(s)://` and `file://`, so `<img src="http://169.254.169.254/...">` or `<a rel="attachment" href="file:///etc/passwd">` work.

**B7 🔴 FSP ID can be claimed without proof of ownership.**
`apps/fsp_sync/views.py:129-139`: the first claimer wins. Relinking keeps the old `participant_id` but imports the new ID's results (`:69-100`).

**B8 🟠 Insecure defaults.**
- `config/settings.py:8-13`: default `SECRET_KEY`; `DEBUG`, `DEMO_MODE` and `ALLOWED_HOSTS=['*']` all on by default.
- `check --deploy` reports 6 warnings.
- DRF's default **BasicAuthentication** is active **[verified]** and advertised in OpenAPI.
- There is no throttling anywhere: login, register, verify, FSP sync, offers and resume are all open.

**B9 🟠 IDOR on positions and offers.**
- `PositionSerializer.company` is writable (`matching/serializers.py:31`). A `PUT` can move a position to another tenant.
- `POST /offers` accepts any `position_id` (`outreach/views.py:77`).
- `why_you` comes from the client (`:78`).

### Data integrity & business logic

**B10 🔴 Profile Strength inflates without bound.** *(Formula is ML; idempotency and storage are yours.)*
- `apps/fsp_sync/views.py:103-108` adds the boost on **every** sync. `POST /api/fsp/sync` is unthrottled.
- `assessment/views.py:282,292` overwrites strength with `50+25θ` and wipes the boost.
- `tests/test_grade_immutability.py:88` asserts the buggy growth.

**B11 → moved to [ML.md](ML.md) (ML-F1, ML-F2).** Constant answer keys and non-IRT grading.

**B12 🔴 Assessment session lifecycle.** All in `apps/assessment/views.py`:
- **Deadline not enforced** (`:215-228`).
- **No finish or abandon.** One unanswered session blocks **every** specialization forever (`:109-111` checks `IN_PROGRESS` globally).
- **Wrong item pool.** Frontend candidates get backend items (`:123-126`).
- **No input validation** for `specialization`, `claimed_grade` and `mode` (`:99-101`).
- **No `atomic` or `select_for_update`.** Concurrent starts create duplicate sessions; concurrent answers can double-finalize.
- **Time travel corrupts stored timestamps.** The demo clock offset is written into `answered_at`, `finished_at`, `deadline_at` and `confirmed_at`.
- **Cooldown on every outcome.** The 30-day cooldown is set even after a *confirmed* result (policy: only after a failed claim).

**B13 🔴 Quickstart broken.**
`config/wsgi.py` and `asgi.py` are missing, so `runserver` fails **[verified]**.

**B14 🔴 SSE is a stub.**
`apps/outreach/views.py:209-224` returns 406 to `EventSource` because only `JSONRenderer` is configured **[verified]**. Otherwise it sends 3 pings, holds a sync worker for 3 s, and never publishes an event.

**B15 🟠 Salary validation bypass leads to 500.**
- `attrs.get('salary_min') or instance.salary_min` (`matching/serializers.py:52-53`, `outreach/serializers.py:44-45`) treats `0` as missing **[verified]**, so the request reaches the DB constraint and returns 500 instead of 422.
- `POST /offers` bypasses serializers (`outreach/views.py:57-79`). `int("abc")` gives 500, `salary_type` silently defaults to `gross`, and `contact_channel` isn't validated.

**B16 🟠 Offer state machine holes.**
- `version` is optional (`outreach/views.py:120,143,170,199`), which bypasses optimistic locking.
- `decline_reason` is unvalidated; >20 chars gives a 500.
- `expires_at` is never enforced.
- After `accepted → interview`, employers lose contacts (`serializers.py:68` checks the status, not the grant).
- `except Exception` swallows errors (`:64,81`).

**B17 🟠 Seed not idempotent.**
- `seed.py:398` uses `hash()`, which is randomized per process, so each run duplicates `FSPResult` rows.
- The seed's events don't match `MOCK_REGISTRY`, so Anna ends up with conflicting placements after a sync.
- `--mode=full` is the same as `mini`.

**B18 🟠 Error handler problems.**
- `core/errors.py:177-187` puts `str(response.data)` in `detail`, which leaks a Python repr **[verified]**.
- It drops `Retry-After`, `Allow` and `WWW-Authenticate`.
- `code=api_error` for 405, 406 and 415.
- `FSPAPIError(errors=serializer.errors)` passes a dict where `[{field, msg}]` is expected (`profiles/views.py:44`, `assessment/views.py:208`, `matching/views.py:48,70,95`).
- `salary_invalid` is used for every position validation error.

### Performance

**B19 🟠 Pool and search are N+1 and unpaginated.**
`matching/views.py:122-154` loads every visible candidate, filters blocklists in Python, and runs about 9 queries per candidate (scorer plus serializer). With the 1,500-candidate full seed that's about 13,500 queries per request, against a p95 target of < 300 ms. Search is unpaginated. `GET /offers` writes an `AuditLog` row and runs 3+ queries per accepted offer.

### Medium

- **B20 🟡 Consents.** `profiles/views.py:63-80` uses `bool("false")`, which is `True`. There is no transaction and no role check. Revocation doesn't hide the profile or close offers.
- **B21 🟡 Verify endpoint.** `/verify/{public_id}` always returns `valid: true`, ignores consent, and uses unordered `.first()`. `public_id` has 24 bits of entropy, and the endpoint is public and unthrottled. Collisions give a 500.
- **B22 🟡 Resume endpoint.** *(Parsing → AI.md.)* No size or MIME limit; parses synchronously in the request thread; masks every exception with fake text.
- **B23 🟡 Taxonomy pollution.** *(Normalization → AI.md.)* `profiles/serializers.py:179-181` creates `Skill` rows from arbitrary input. The delete-then-recreate is not atomic.
- **B24 🟡 Non-deterministic league.** `.first()` on unordered `LeagueMembership` (`profiles/serializers.py:85-87`, `matching/serializers.py:83`, `profiles/views.py:122`, `pdf_service.py:31`).
- **B25 🟡 Time travel.** `int()` on raw input gives a 500. Negative and huge offsets are accepted. `/demo/reset` is missing.
- **B26 🟡 PDF fallback.** Returns HTML named `.pdf` on any WeasyPrint failure.
- **B27 🟡 FSP task.** `fsp_sync/tasks.py:17-18` swallows exceptions. The invariant check is an `assert` (`fsp_sync/views.py:109`), which is stripped under `-O`.
- **B28 🟡 Profile validation.** Salary range (`min ≤ max`) and `blocked_company_ids` aren't validated.
- **B29 🟡 Side effect on GET.** `CandidateMeView.get` creates the profile.

---

## 5. Code Quality & Django Conventions

- **C1.** Hand-rolled `APIView`s with manual `is_valid()` handling. Use `GenericAPIView`/ViewSets with user- or company-scoped `get_queryset()` and `is_valid(raise_exception=True)`. drf-spectacular reports 7 "unable to guess serializer" errors.
- **C2.** Many endpoints read `request.data.get()` with no serializer: offers, assessment start, consents, persona, time travel, FSP link.
- **C3.** Serializers are declared in `identity/views.py`. `UserSerializer` is unused, and responses are hand-built dicts.
- **C4.** Mid-module imports (E402 ×7) and local imports inside functions.
- **C5.** String literals instead of `core.enums` (`core/permissions.py`, `identity/views.py:150`, `outreach/services.py:146`).
- **C6.** The company lookup is duplicated 3× in `identity/views.py`.
- **C7.** 10 `SerializerMethodField`s lack `@extend_schema_field`, so the frontend's generated types become `string`. **This directly hurts FE.**
- **C8.** `get_consents` runs 3 queries per call.
- **C9.** Dead or never-maintained fields: `ItemFamily.exposures`, `Position.weights`, `Offer.match_snapshot`, `promotion_unlocked`, `counts_as_attempt`, `percentile`, `next_promotion_at`, `completeness`, `last_active_at`, `Identity`, and `revoke_grant` (no caller).
- **C10.** Inline choices `Position.status` and `FSPResult.format`.
- **C11.** Missing constraints and indexes: one in-progress assessment per candidate and spec (partial unique); `contact_grants(company_id, candidate_id) WHERE revoked_at IS NULL`.
- **C12.** `AuditLog` and `OfferEvent` are documented as immutable but nothing enforces it.
- **C14.** ruff reports 516 issues (44 unused imports, 55 unsorted import blocks, 7 E402, 5 unused variables, `try/except/pass`). No ruff config, no pre-commit, **no CI**.
- **C15.** Partial type hints. The `timezone.datetime` annotation only works by accident.
- **C16.** No `admin.py`, yet admin is mounted.
- **C17.** `requirements.txt` has no pins and mixes test dependencies into runtime.
  - **Unused:** `valkey`, `redis`, `django-eventstream`, `authlib` (until A8), `pgvector` (until A12), `Jinja2`, `django-celery-beat` (not installed as an app), `python-dotenv`, `pytest-asyncio`, `factory-boy`.
  - **Missing:** `pytest-cov`, `ruff`.
  - ML and AI will add `numpy`, `scipy`, `rapidfuzz`, `gigachat` and others in their own PRs. Review them.
- **C18.** pytest config is duplicated in `pytest.ini` and `setup.cfg`. The root `conftest.py` fixtures are unused.
- **C19.** `.agents/` adds 511 files (Rust, Vue, PHP and other irrelevant rules), plus `ecc-install-state.json` with foreign absolute paths.
- **C20.** 18 tests, only 4 of them over HTTP. **Untested:** auth, persona, the assessment flow, cooldowns, pool visibility, consent revocation, salary 422 via the API, FSP sync idempotency, seed idempotency, SSE, PDF, tenant isolation.
- **C21.** One test asserts the buggy strength growth. A docstring cites the non-existent `tests/test_invariants.py`.
- **C22.** Tests rely on the `sys.path` hack, and there are no factories.

---

## 6. Documentation Inconsistencies (backend-owned)

ML owns the IRT and scoring sections (D5, D10–D12 → ML.md). You own the rest.

- **D1.** README quickstart Step 5 fails (B13).
- **D2.** `docs/openapi.json` is actually **YAML**. It is stale (`/demo/time-travel`) and advertises `basicAuth`.
- **D3.** README says gross/net is "mandatory", but offers default to `gross`.
- **D4.** README says "every unauthorized read is logged". Not on `/talent/{public_id}` (B5).
- **D6.** README ReasonChips names `verified_by_test` and `verified_by_fsp`. The code emits `test`, `fsp` and `declared`.
- **D7.** The README error catalog omits `assessment_in_progress`, `candidate_not_reachable`, `bad_credentials`, `assessment_expired`, `not_finished`, `forbidden`, `not_found` and `api_error`.
- **D8.** README claims an idempotent seed with 4 FSP profiles (B17).
- **D9.** No env var docs. `DEMO_MODE` defaults to on.
- **D13.** `BACKEND.md` §3.2 shows a 14-day expiry that doesn't exist.
- **D14.** `BACKEND.md` §6 calls the PDF "protected", but it has no signature and `/verify` always returns valid.
- **D15.** `BACKEND.md` §7 says to run `celery beat`, but there is no schedule. It also claims percentile recompute.
- **D16.** `BACKEND.md` lines 227 and 238 link to `file:///c:/Users/bikhe/...`.
- **D17.** ARCHITECTURE §2.10 is labeled "current Django MVP" but lists about 13 unimplemented endpoints and omits implemented ones (`/fsp/link`, `/fsp/sync`, `/positions/{id}`, `/offers/{id}`, `/assessments/{id}/answers|result`).
- **D18.** ARCHITECTURE §0 (line 13), §2.7 (line 198) and §4 (line 360) still say FastAPI and Valkey.
- **D19.** ARCHITECTURE §2.3 module map and §2.1 layering don't match the code (A1, A3).
- **D20.** ARCHITECTURE §2.13 omits `.agents/` and `web/` (A13).
- **D21.** `TASKS.md` has the false `[x]` claims below, and the original "Done:" criteria were deleted:

| Task | Claim | Reality |
|---|---|---|
| F-01 | CI configs | None in repo |
| F-05 | exported and validated | YAML named `.json`, stale |
| F-08 / BE-13 | idempotent; full seed | Non-idempotent; `full` = `mini` |
| BE-01 | verify-email, rate limit, "tested in `apps.identity`" | Missing; no tests there |
| BE-02 | visibility rule tested | Broken (B4); untested |
| BE-03 | resume parse | Hardcoded (B22; AI-07 now) |
| BE-05 | HMAC seed, deadline | SHA-256; not enforced (B12) |
| BE-06 | percentiles | Never computed |
| BE-08 | "tested in `apps.matching`" | No tests |
| BE-10 | SSE | 406 (B14) |
| BE-11 | FSP ID | No OIDC (B7, A8) |
| BE-12 | Jury mode | No reset; persona backdoor (B3) |
| BE-14 | RBAC matrix, CSRF, rate limits | 4 HTTP tests |
| BE-16 | API docs & SBOM | No SBOM |

- **D22.** `TASKS.md` §1.4 says to send `X-Requested-With: fsp-draft` as the CSRF guard. Django needs `X-CSRFToken` (G1).

---

## 7. What Is Solid (keep)

- App split and migrations are consistent.
- DB `CheckConstraint`s on salaries; unique constraints on identity, skill source, FSP result, shortlist, grant source and league.
- The contact vault is separate from the profile, and `ContactAccessService` is the single read gate (once B5 is fixed).
- `OfferService.transition` (`atomic` + `select_for_update` + version check + `F('version') + 1` + `OfferEvent` + `AuditLog`) is **the pattern to copy** into the assessment and FSP services.
- `ItemViewSerializer` never exposes `key`.
- The RFC 7807 envelope, Argon2, HttpOnly SameSite cookies, and a custom user model from day one.

---

## 8. Action Items (Checklist)

**P0** blocks the demo or is a security issue. Do it first, in roughly this order. **P1** is the golden path to M1 and unblocks ML, AI and FE. **P2** is hygiene. Each fix ships with a failing-first test (TDD, per `AGENTS.md`).

### P0: Must fix before any demo or deploy

- [x] **Add `config/wsgi.py` and `config/asgi.py`** (standard templates), plus a smoke test that imports `config.wsgi.application`. *(B13, D1)* **Status 2026-10-09:** smoke test → R26.
- [ ] **Commit `.env.example` and secure settings.** `config/settings.py:8-13`: `DEBUG` and `DEMO_MODE` default to `False`. Require `SECRET_KEY` and `ALLOWED_HOSTS` when not in debug, and fail fast if missing. Add `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_*` and `CSRF_TRUSTED_ORIGINS` from env, and call `load_dotenv()`. Use the variable names from `TASKS.md` §1.2. *(B8, A10, G1)* **Status 2026-10-09:** → R2, R23.
- [ ] **DRF defaults** (`config/settings.py:107-122`): `SessionAuthentication` only (drop Basic), `IsAuthenticated` by default, and `DEFAULT_THROTTLE_CLASSES` with scoped rates for `login`, `register`, `verify`, `fsp_sync`, `offers` and `resume`. *(B8)* **Status 2026-10-09:** Session-only + IsAuthenticated done; throttles → R1.
- [x] **Add `GET /api/auth/csrf`** (`ensure_csrf_cookie`). *(G1)* **Status 2026-10-09:** H4.
- [x] **Remove company auto-creation** (`apps/matching/views.py:16-28`). Raise 403 `company_required` when an employer has no membership; create companies via `POST /api/companies` (G17) or the seed. Set `IsEmployer` on `OfferWithdrawActionView`, and handle the admin branch of `OfferListCreateView.get` explicitly. Add a test with two employers who share an email local part. *(B1)* **Status 2026-10-09:** tests → R26; races → R20.
- [x] **Restrict self-registration roles** (`apps/identity/views.py:23`) to candidate and employer. *(B2)* **Status 2026-10-09:** test → R26.
- [x] **Lock down the demo persona** (`apps/identity/views.py:164-214`): a strict `ChoiceField` with the 3 personas, require `is_demo=True`, no known-password creation (use `set_unusable_password()` in the seed), and keep it disabled unless `DEMO_MODE`. *(B3)* **Status 2026-10-09:** tests → R26.
- [ ] **Create `apps/profiles/selectors.py` with `visible_candidates_for(company)`.** Use the latest consent per type (`Subquery` ordered by `-created_at`, or a denormalized `publication_granted` column), `open_to_offers`, a verified email, league status not `pending`, and `~Q(blocked_company_ids__contains=[company.id])`. Use it in pool, search, talent card and `create_offer`. Test that revoking publication removes the candidate everywhere. *(B4, B5, TASKS §1.3 invariant 1)* **Status 2026-10-09:** → R5.
- [x] **Talent card** (`matching/views.py:232-255`): 404 unless the candidate is visible. Always call `get_contacts()` and catch `ContactNotGranted`, so denials are audited. *(B5)* **Status 2026-10-09:** catch only ContactNotGranted → R4.
- [ ] **PDF safety** (`apps/profiles/pdf_service.py`): escape all values (or move to a Django template with autoescape), use `HTML(..., url_fetcher=<data:-only fetcher>)`, and return 503 instead of HTML-as-PDF. Add a test with a malicious skill name. *(B6, B26)* **Status 2026-10-09:** → R7.
- [x] **FSP linking** (`apps/fsp_sync/`): move logic to `services.py`. Outside DEMO_MODE, accept a participant ID only from a verified OIDC `id_token` (AI-08 mock). Handle relinking with a 409 or a clean replacement. Wrap in `atomic`, and map `IntegrityError` to `fsp_id_already_linked`. *(B7, A8)* **Status 2026-10-09:** H1, H2; atomic sync → R14.
- [x] **Idempotent strength.** Add `base_strength` and `fsp_boost` fields to `LeagueMembership` (migration). Add `recompute_strength(user)` that sets `strength = clamp(base + boost)` from scratch every time. Interim boost: `min(15, 5 × results)`, computed fresh, until ML's `fsp_boost()` lands. Call it from FSP sync and assessment finalize. Fix `tests/test_grade_immutability.py` to assert that two syncs give the same strength. *(B10)* **Status 2026-10-09:** backfill heuristic → R14.
- [ ] **Assessment lifecycle** (`apps/assessment/views.py` → new `assessment/services.py`): **Status 2026-10-09:** H5–H7 fixed; rest → R9–R13.
  - Add `StartAssessmentSerializer` (`ChoiceField`s).
  - Make the in-progress guard per specialization, and auto-expire stale sessions.
  - Enforce `deadline_at`: late answers count as incorrect.
  - Add `POST /assessments/{id}/finish` (abandon rules).
  - Pick families by spec only, and return 409 `no_item_bank` if there are none.
  - Wrap start, answer and finalize in `atomic` + `select_for_update`.
  - Use the demo clock only for cooldown comparisons.
  - Apply the cooldown only after a failed claim.

  *(B12, G5 partially)*
- [ ] **SSE.** Add `EventStreamRenderer(media_type='text/event-stream')` on the view. Publish `offer.*`, `league.updated` and `fsp.synced` via Redis pub/sub from the services. Serve it from ASGI (uvicorn/daphne) or a dedicated process so sync workers aren't tied up. Send a keepalive every 15 s. If time is short, tell FE1 to keep the polling fallback, and return 501 instead of a fake stream. *(B14, G12)* **Status 2026-10-09:** scoping + on_commit fixed (H8); transport → R24.
- [ ] **Salary validation.** Use `attrs['x'] if 'x' in attrs else getattr(self.instance, 'x', None)` in both serializers, make `company` read-only, and add API tests: `salary_min=0` → 422 `salary_invalid` on create and update. *(B15, B9)* **Status 2026-10-09:** company read-only fixed (H3); codes, DB check, tests → R16.
- [x] **`CreateOfferSerializer`.** Required `salary_type` (no default), `ChoiceField(ContactChannel)`, validated integers, and `position` limited to the employer's company. Compute `why_you` and `match_snapshot` server-side from the scorer, ignoring client input. *(B9, B15, A7)* **Status 2026-10-09:** done.
- [x] **`OfferActionSerializer(version required, reason ∈ DeclineReason)`.** In `transition()`, reject `now > expires_at` (transition to `expired`, then raise `InvalidTransition`). *(B16)* **Status 2026-10-09:** expiry H9.
- [x] **Seed.** Use stable event IDs matching the registry data, wrap in `transaction.atomic()`, and add a test that runs the seed twice and checks identical counts. Reject `--mode=full` until BE-13 is implemented. *(B17)* **Status 2026-10-09:** done.
- [x] **Commit `docs/openapi.json` as real JSON** (`manage.py spectacular --format openapi-json --file docs/openapi.json`), plus a CI drift check. FE generates its client from it. *(D2)* **Status 2026-10-09:** full drift check → R25.

### P1: Golden path (M1) and unblocking the other streams

- [ ] **Service and selector layer:** `assessment/services.py`, `matching/services.py` + `selectors.py`, `profiles/services.py` and `fsp_sync/services.py`. Views only validate, call a service and serialize. Move `ContactAccessService` out of `core` (into `outreach` or a `privacy` app) so `core` imports nothing from the domain apps. *(A1, A2)* **Status 2026-10-09:** → §9.3 #1, #2.
- [ ] **Integrate ML's `CatEngine`** behind `assessment/services.py`: persist `CatState`, serve `max_items`, `level` and `format`, and map `CatResult` to `AssessmentResult` (`rating_ci`, `topics`, `evidence`, `fallback`, `next_attempt_at`). Add `POST /assessments/{id}/fallback`. Add `manage.py sync_families` to upsert `ItemFamily` rows from ML's registry. *(A5, G5)* **Status 2026-10-09:** → §9.3 #2.
- [ ] **Pool and search rewrite.** **Status 2026-10-09:** → §9.3 #1, R18.
  - SQL hard filters.
  - `prefetch_related` and `select_related` with one batched load into `CandidateCtx`/`NeedCtx` (ML DTOs), then `score_pool()`.
  - Pagination, facets, query params, `components` as a list, and `gaps`.
  - `relaxations: []` until ML's P1.
  - A query-count test (`django_assert_max_num_queries`).
  - A p95 check on the full seed.

  *(B19, A6, G8, G9)*
- [ ] **`recompute_league(spec, grade)`** using ML's `percentiles()` and `strength()`. Trigger it after finalize and after FSP sync, and emit `league.updated`. *(A4, BE-06)* **Status 2026-10-09:** → §9.3 #3.
- [ ] **Offer contacts depend on the grant, not the status.** Show contacts whenever an active grant exists (so they survive `interview`, `hired` and `closed`). Remove `except Exception`. Batch the audit writes on list. Add `talent: TalentShort` and `decline` to the employer view. *(B16, B19, G10)* **Status 2026-10-09:** grant-based done; audit spam → R4.
- [x] **Offer lifecycle:** `interview`, `hired` and `close` employer actions. A Celery beat `expire_offers` task registered in `CELERY_BEAT_SCHEDULE`. `django_celery_beat` in `INSTALLED_APPS`, or remove it. Import the Celery app in `config/__init__.py`. An `llm` queue for AI tasks. *(A7, A11)* **Status 2026-10-09:** beat can't start in compose → R23.
- [x] **Error handler** (`apps/core/errors.py:164-187`): take `detail` from `response.data['detail']`, copy headers, map 405/406/415 codes, and use one `[{field, msg}]` shape via a single helper. Stop using `salary_invalid` for generic validation errors. *(B18, G13)* **Status 2026-10-09:** Retry-After on cooldown → R15.
- [x] **Consents:** `ConsentUpdateSerializer`, `atomic`, candidate-only. On publication revoke, withdraw pending offers via `OfferService` and audit it. *(B20, BE-02)* **Status 2026-10-09:** error handling → R15.
- [ ] **`/verify/{public_id}`:** respect consent, return the confirmed league for an explicit specialization, add `issued_at`, throttle it, and use ≥ 8 hex chars for `public_id` with retry on collision. *(B21)* **Status 2026-10-09:** → R9, R19.
- [ ] **Resume and JD endpoints:** ≤5 MB, PDF MIME check, a Celery task on `llm` calling AI's `parse_resume`/`parse_jd`, a 15 s wait then the rules result, and error `unreadable_pdf`. Add `POST /api/positions/parse`. *(B22, G6, AI.md)* **Status 2026-10-09:** → §9.3 #4, R21.
- [ ] **Taxonomy:** `manage.py sync_taxonomy` (AI's `content/skills.yaml` → `Skill`). Profile skills go through `normalize_skill()`; return unknown terms instead of creating rows; wrap the update in `atomic`. Add `GET /api/taxonomy`. *(B23, G3)* **Status 2026-10-09:** → §9.3 #5.
- [ ] **Profile validation** (salary range, `blocked_company_ids`); `LeagueMembership.Meta.ordering` or always filter by spec; no profile creation on GET. *(B24, B28, B29)* **Status 2026-10-09:** → R19, §9.3 #6.
- [ ] **Identity:** `POST /api/auth/verify-email` (signed token, `verify_link` in DEMO_MODE), `POST /api/demo/reset`, and time travel validated via `IntegerField(min_value=0, max_value=365)`. *(G2, G4, B25)* **Status 2026-10-09:** verify-email done in DEMO_MODE; → R17, §9.3 #6.
- [x] **`GET /api/leagues?specialization=`** (shelf counts). *(G7)* **Status 2026-10-09:** done.
- [x] **`GET /api/positions/{id}/shortlist`**, `POST /api/companies`, and `GET /api/companies?search=`. The company create endpoint must land together with the B1 fix. *(G16, G17)* **Status 2026-10-09:** → R5, R20.
- [x] **`GET /api/lab/report`** (BE-22) serving ML's report or fixture. *(G11)* **Status 2026-10-09:** → R21.
- [x] **AI-08 `fsp-id-mock` + Authlib client:** `GET /api/auth/fsp-id/login?intent=`, `/callback`, PKCE, `identities` upsert, 409 `fsp_id_already_linked`; registry data from ML's synthetic world. *(A8, G15)* **Status 2026-10-09:** H1.
- [ ] **pgvector migration** (`CREATE EXTENSION vector`, `VectorField(1024)` on profiles and positions, HNSW index) when ML starts AI-11. *(A12)* **Status 2026-10-09:** → §9.3 #7.
- [ ] **`seed --mode=full`** loads ML's `seed_data/full/` (BE-13). Target: under 60 s on an empty DB. **Status 2026-10-09:** → §9.3 #8.
- [ ] **F-02:** `docker-compose.yml` (db=`pgvector/pgvector:pg17`, redis, api, worker, worker-llm, beat, web), `Makefile` (`dev, up, migrate, seed, test, openapi, verify, validate`), healthchecks, migrate + seed on boot. **Status 2026-10-09:** files exist but the stack is broken → R23.
- [ ] **API-level tests:** `tests/test_auth.py`, `test_tenant_isolation.py`, `test_pool_visibility.py`, `test_assessment_flow.py`, `test_offers_api.py`, `test_fsp_sync.py`, `test_seed.py` and `test_salary_api.py`. Add `pytest-cov` and a coverage gate. *(C20)* **Status 2026-10-09:** → R26, R25.
- [ ] **BE-15:** staging on a Russian VPS, HTTPS (Caddy), deploy from `main`, nightly `pg_dump`. **Status 2026-10-09:** → §9.3 #9.

### P2: Conventions, hygiene, docs

- [ ] Convert views to `GenericAPIView`/ViewSets; add request serializers everywhere; move serializers out of views; put imports at module top; use enums instead of literals; add `@extend_schema_field` on every `SerializerMethodField` (FE types depend on it). *(C1–C8)*
- [ ] `apps.<name>` package layout and removal of the `sys.path` hack, coordinated with ML and AI. *(A9)*
- [ ] Model cleanup: enums for inline choices; partial unique constraint for in-progress assessments; grant index; enforce `AuditLog`/`OfferEvent` immutability; implement or remove the dead fields. *(C9–C12)*
- [ ] Replace the invariant `assert` with an exception. Celery tasks use `autoretry_for` and logging, never `except: pass`. *(B27)*
- [ ] Admin registrations (read-only audit, offer events and grants), or remove admin. *(C16)* **Status 2026-10-09:** → R3.
- [ ] Tooling: `pyproject.toml` with ruff; fix the auto-fixable issues and F401/E402/F841; pre-commit. A GitHub Actions workflow: `ruff`, then `check --deploy` (prod env), then `makemigrations --check`, then `pytest --cov` (`postgres:17` service), then the OpenAPI drift check, then FE `pnpm typecheck && pnpm build` (paths under `web/`). *(C14)* **Status 2026-10-09:** ruff + CI exist; → R25.
- [ ] Split requirements into `base`/`dev`, pin versions (`uv lock` or `pip-compile`), remove unused packages, and delete the duplicate pytest config and unused fixtures. *(C17, C18)*
- [ ] Prune `.agents/` to the referenced rules; drop `ecc-install-state.json`. *(C19)*
- [ ] P1 backend features from `TASKS.md`: BE-17 vacancies and applications, BE-18 micro-tasks, BE-19 anti-fraud (credits, salary sanity, INN checksum), BE-20 contact revocation, floor warning and Need Health, BE-21 contacts encrypted at rest and PDF watermark, BE-23 Locust load test.
- [ ] **Docs:**
  - **README:** quickstart, env table, ReasonChips names, error catalog, seed claims.
  - **BACKEND.md:** fix §3.2, §6 and §7, and the `file:///` links; §4–§5 are ML's.
  - **ARCHITECTURE.md:** split §2.10 into Implemented and Planned; fix the §0, §2.7 and §4 FastAPI/Valkey mentions; update the §2.3 module map; add `web/` to §2.13.
  - **TASKS.md:** restore the "Done:" criteria and un-tick unmet items (D21); fix the CSRF header in §1.4 (D22); record the owners from §0 of this file.

  *(D1–D22)*
- [ ] Fix the docstring reference to `tests/test_invariants.py` (`apps/assessment/models.py:162`).

---

## 9. Status after the PR #2 review (2026-10-09): START HERE

PR #2 (`bikhe-p0-backend-fixes`) was reviewed by four review agents, and the bugs were reproduced with failing tests on Postgres. About 70% of P0 was done well. The critical bugs were fixed in the hotfix PR from branch `fix/be-critical-hotfixes` (§9.1). **Start only after it is merged, and pull `main` first.** Then do §9.2 (rework) and §9.3 (remaining tasks) in order. §8 is ticked to match: `[x]` is done; an open item points to its R-ID.

### 9.1 Fixed in the hotfix PR (don't redo; keep these tests green)

| ID | Bug | Fix |
|---|---|---|
| H1 | **FSP ID account takeover.** The mock IdP was mounted in prod. When the token exchange failed, the client signed its own id_token, so anyone could log in as any FSP-linked user. | `fsp_mock` views return 404 unless `DEMO_MODE`. PKCE is mandatory, and `redirect_uri` must be our callback. `identity/oidc.py` has no fallback: an IdP error gives 400 `token_exchange_failed` or 502 `fsp_id_unavailable`. The id_token is checked against the IdP JWKS (`jwks_uri`): RS256 only, plus `iss`, `aud`, `exp` and `nonce`. The nonce is also compared explicitly. The callback pops state, nonce and verifier (single use). `Identity.subject` is the IdP `sub`, and the email counts as verified only if `email_verified` is true. Login never attaches FSP to an existing email account (409 `account_exists`), and user creation is atomic. The mock signing key is shared by all workers (`FSP_MOCK_PRIVATE_KEY_PEM`, or `var/fsp_mock_rsa.pem`). New setting `OIDC_INTERNAL_URL`. Compose sets `OIDC_ISSUER` and `OIDC_INTERNAL_URL` for the in-app mock. |
| H2 | `POST /api/fsp/link` accepted any participant ID (B7) | 403 `fsp_oidc_required` outside `DEMO_MODE`. Linking means OIDC `intent=link`. |
| H3 | A position could be moved to another company (B9) | `PositionSerializer.company` is read-only. On create it comes from the caller's membership. |
| H4 | The CSRF cookie was HttpOnly, so the SPA could not send `X-CSRFToken` (G1) | `CSRF_COOKIE_HTTPONLY = False` |
| H5 | A late answer rolled back finalize, leaving the session stuck for 24 h. All deadlines were counted from start. | The deadline is set when an item is served (`_serve_item`). A late answer (past deadline + 3 s) is recorded as incorrect and the test continues. Items not yet served have `deadline_at = null`. |
| H6 | Instant fallback confirmed the lower grade with zero evidence, and short_test could be repeated without limit | Instant is allowed only for a session that was not abandoned and whose own re-score is at least the lower grade. Otherwise 409 `fallback_not_eligible`. short_test works once per session (409 `fallback_already_used`). The result's `fallback` hint uses the same check (`AssessmentService.fallback_offer`). |
| H7 | Concurrent starts created duplicate sessions | Partial unique constraint `uq_one_in_progress_assessment_per_spec` (migration `assessment/0004`). `IntegrityError` maps to `assessment_in_progress`. |
| H8 | SSE broadcast every tenant's events and replayed the last 100 to anyone | `outreach/events.py` takes the audience from the payload: `candidate_id` equals the user, or `company_id` is one of the user's companies. It fails closed, and replay is scoped. Dispatch happens in `transaction.on_commit`. `limit` is validated before streaming (422). |
| H9 | Lazy offer expiry was rolled back, and any offer past `expires_at` was frozen (e.g. accepted → interview) | Expiry applies only to sent/viewed offers. The expiry, `OfferEvent`, `AuditLog` and event are persisted before raising 409 `offer_expired`. |

- **Tests:** `tests/test_security_hotfixes.py`, `test_assessment_lifecycle.py` and `test_sse_and_expiry.py`. The OIDC tests now go through the real token endpoint: they patch `identity.oidc._http_post_form` and `_http_get_json`.
- **FE contract changes:** new error codes `offer_expired`, `fallback_not_eligible`, `fallback_already_used`, `account_exists`, `fsp_oidc_required` and `fsp_id_unavailable`. `Position.company` is read-only.

### 9.2 Rework from the review (do next, in this order; failing test first)

**Security and privacy**
- **R1. Throttles are configured but not attached.**
  - Set `throttle_scope`: `login` on `LoginView`, `register` on `RegisterView`, and `fsp_sync` on `FSPLinkView` and `FSPSyncTaskTriggerView`.
  - Set `offers` on `OfferListCreateView` for POST only (override `get_throttles`).
  - Set `resume` on `ResumeParseView`; `PositionParseView` gets its own `jd_parse`.
  - Add `CACHES` = `RedisCache(REDIS_URL)` so limits are shared across workers. Set `NUM_PROXIES` from env.
  - Test: the (N+1)-th login gets 429 with `Retry-After`.
- **R2. Secrets.**
  - `ITEM_SEED_SECRET` must fail fast when `DEBUG=False`, like `SECRET_KEY`. Remove the fallback in `assessment/services.py`.
  - Remove the `SECRET_KEY` and `ITEM_SEED_SECRET` defaults from `docker-compose.yml`; use `env_file`.
  - Add `OIDC_INTERNAL_URL` and `FSP_MOCK_PRIVATE_KEY_PEM` to `.env.example`.
  - Add a system check that warns when `DEMO_MODE and not DEBUG`. In DEMO_MODE the mock IdP lets anyone log in as any FSP participant, so a demo host must never hold real users.
- **R3. Admin leaks.**
  - `AssessmentItemAdmin`: exclude `key`, `fingerprint` and `seed`; no add or change.
  - Unregister the `CandidateContact` admin.
  - `LeagueMembership`, `AssessmentSession`, `AuditLog`, `OfferEvent` and `ContactGrant` admins become read-only.
- **R4. Contact reads.**
  - Talent card: catch only `ContactNotGranted`, not `Exception`.
  - `OfferSerializer.get_candidate_contacts`: call `has_active_grant()` first and `get_contacts()` only when granted. Today `GET /offers` writes N false-denial `AuditLog` rows.
- **R5. Visibility (B4/B5).**
  - One rule in `profiles/selectors.py`, shared by the queryset and `is_candidate_visible_to_company`:
    - the latest publication consent is granted
    - `open_to_offers` is set
    - the email is verified
    - at least one non-pending league exists (`Exists(...)`)
    - the blocklist is applied in SQL: `~Q(blocked_company_ids__contains=[company.id])`
    - ordering is deterministic: `order_by(..., 'id')`
  - Shortlist `PUT` and `POST /offers` return the same 404 for invisible and nonexistent candidates.
  - Test: after revoking publication consent, the candidate is gone from pool, search, card, shortlist and offer.
- **R6. Login CSRF.** DRF doesn't CSRF-check anonymous `login`, `register` or `demo/persona`; add `@method_decorator(csrf_protect)`. Test with `APIClient(enforce_csrf_checks=True)` (this also covers H4).
- **R7. PDF (B6/B26).** Return 503 on `ImportError` too. Add the malicious-skill test (`<img src="file:///etc/passwd">`, `http://169.254.169.254/`).
- **R8. Employer-facing payloads carry no internal UUIDs.**
  - Talent-card assessment IDs and the `candidate_id` in SSE events sent to employers become `public_id`.
  - Non-blind `display_name` currently shows `full_name`: confirm with product.

**Assessment and data integrity**
- **R9. A failed promotion or abandon overwrites a confirmed grade** (`finalize_assessment`).
  - If the league is CONFIRMED at grade G, a failed higher claim keeps G and CONFIRMED. The attempt is stored on the session only.
  - Clear `confirmed_at` whenever the status becomes unconfirmed.
  - `/verify` never returns `valid: true` for unconfirmed.
- **R10.** An unconfirmed session stores `result_grade = claimed_grade`. Store the scorer's achieved grade instead, and show `decision` next to it on the talent card.
- **R11. Abandon and stale rules (ARCHITECTURE §2.5).**
  - `/finish` and the stale-session sweep count as an attempt (finalize unconfirmed plus cooldown) only if at least 50% of items were answered. Otherwise the session becomes `ABANDONED`/`EXPIRED` with no cooldown.
  - Use `AssessmentStatus.ABANDONED`.
  - `EligibilityView` checks in-progress sessions per specialization.
- **R12. Request validation.**
  - `StartAssessmentSerializer`: required fields, and `mode` from `AssessmentMode.choices` (today `'trial'` doesn't match `'express'`).
  - `AnswerRequestSerializer.validate()` requires `option_id` or `value`.
  - The short-test session gets `kind=FALLBACK, counts_as_attempt=False`.
  - The instant-fallback membership `get_or_create` derives `base_strength` from θ, as `finalize_assessment` does.
- **R13.** `GET /assessments` shows `evidence[].correct` while a session is in progress. Show it only when finished.
- **R14. FSP sync (`fsp_sync/services.py`).**
  - Wrap `sync_fsp_data` in `atomic`.
  - On a registry miss, set `sync_status` to `NOT_FOUND`/`FAILED` and keep the old results.
  - Delete results the registry no longer returns.
  - Replace the `base==0 and strength>0` backfill with a one-off data migration, and delete the tautological grade check.
  - `sync_all_fsp_profiles`: `autoretry_for`, `logger.exception` with the IDs, return `{ok, failed}`. Either schedule it in `CELERY_BEAT_SCHEDULE` or delete it.
- **R15. Offers.**
  - `expire_offers` reuses `OfferService._expire_locked` (for the `AuditLog`) and isolates per-row failures.
  - Consent revoke (`profiles/views.py`): catch `InvalidTransition`, `OfferExpired` and `VersionConflict` explicitly. Retry `VersionConflict` once with a fresh version. Use `logger.exception`.
  - Document 409 `offer_expired` in `extend_schema`.
  - `CooldownActive` sends `Retry-After`.
- **R16. Salary (invariant 5).**
  - `salary_invalid` for every salary error on position create/update and on offer create.
  - Add a DB `CheckConstraint` `salary_type IN ('gross','net')` on Position and Offer.
  - API tests: `salary_min=0` gives 422 on create and on update.
- **R17. Demo.**
  - Time travel only for `is_demo` users, and it sets the offset (no `+=`).
  - `/demo/reset` restores the persona's seeded data, not just the clock.
- **R18.** Pool and search take `page >= 1` and `1 <= size <= 100` through a serializer; anything else is 422 (`size=0` is a 500 today).
- **R19.** `public_id` has at least 8 hex characters, with retry on collision (B21). Every `LeagueMembership` `.first()` filters by specialization or relies on `Meta.ordering` (B24).
- **R20. Companies.**
  - `UniqueConstraint` on `CompanyMember.user`, since the `exists()` check races.
  - `GET /api/companies` requires `search` of at least 2 characters and is paginated.
  - Handle the admin branch of `GET /offers` explicitly.
- **R21. No fake data.**
  - A corrupt `report.json` gives a logged 500 `report_unreadable`, never hard-coded metrics.
  - The resume stub returns `source='stub'` with empty skills until AI's `parse_resume` lands.
- **R22.** `EventStreamRenderer` must render error dicts as JSON, so the 403/422 bodies are valid. SSE company scope is read at connect time; that is acceptable, but document it.
- **R22a.** Concurrent first FSP logins for the same participant give a raw `IntegrityError` 500; map it to 409. Reversing migration `assessment/0004` fails once unserved items have `deadline_at = NULL`; backfill in the reverse function or document it as irreversible.

**Infra and CI**
- **R23. Compose is broken.**
  - `worker`, `worker-llm` and `beat` crash because `ALLOWED_HOSTS` is missing. Share one env anchor `x-backend-env: &backend-env` across all Python services.
  - The local stack is HTTP-only. The `api` service already has `SECURE_SSL_REDIRECT=False` (H1 needs it for the IdP self-call); give it to the shared env. Make `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` env-configurable, otherwise the browser drops cookies and login fails.
  - Decouple HSTS and `SECURE_PROXY_SSL_HEADER` from the redirect flag.
  - Remove `seed || true` from the entrypoint.
  - Add `.gitattributes` with `*.sh text eol=lf`.
  - Done means: `docker compose up --build`, then log in with FSP ID in a browser.
- **R24. SSE transport.**
  - Add a Redis subscriber on channel `fsp_events`, so events from other workers and from Celery arrive.
  - Serve `/api/events` from an ASGI worker (uvicorn) or a separate service, so streams don't pin sync gunicorn workers.
  - Send a keepalive every 15 s.
  - If this isn't done by the demo, return 501 and FE keeps polling.
- **R25. CI.**
  - Run on every PR and push.
  - `pytest --cov=apps --cov-fail-under=75`.
  - OpenAPI drift check: regenerate, then `git diff --exit-code docs/openapi.json`.
  - Python 3.13.
  - One pytest config with `testpaths=["tests"]`.
  - Add `LOGGING` (console, INFO).
  - Fix the 6 drf-spectacular warnings (`ENUM_NAME_OVERRIDES`, duplicate operationIds).
- **R26. Missing P0 tests:**
  - wsgi import smoke
  - `role=admin` register gives 400
  - persona: off outside `DEMO_MODE`, unknown persona gives 422, non-demo user is rejected
  - two employers with the same email local part
  - `company_required` gives 403
  - talent card gives 404, plus an `AuditLog` row
- **Docs.** AGENTS.md, ARCHITECTURE.md and the README must say that contact gating lives in `outreach/services.py` (`core/services.py` is a shim). Add the §9.1 error codes to the README catalog.

### 9.3 Remaining backend tasks (after 9.2), with the how

1. **Pool and search rewrite (B19/A6/G8)** in `matching/services.py` + `selectors.py`.
   - SQL hard filters: specialization, grade adjacency, `work_formats`, `salary_max`.
   - One batched query (`select_related`/`prefetch_related`), turned into plain DTO dicts and passed to the scorer.
   - Pagination and facets in SQL.
   - Tests: `django_assert_max_num_queries(15)`, and p95 < 300 ms on 1,500 candidates.
2. **Engine adapter (A5, §2.1).** Create `assessment/engine_adapter.py` with the ML.md §3 interface (`start`, `next_item`, `record`, `result`, `CatState.to_json`), backed by the current stub, so services call only the adapter.
   - Add `manage.py sync_families` and stop the lazy `ItemFamily` `get_or_create(format='choice')`.
   - When ML ships `CatEngine`, swap it in inside the adapter.
   - Never edit the formulas in `assessment/engine.py` or `matching/scoring.py`; write requests in ML.md.
3. **`recompute_league(spec, grade)`** via the adapter (stub: rank-based percentile).
   - Trigger it after finalize and after FSP sync, and emit `league.updated`.
   - Idempotency test.
4. **Resume and JD (B22/G6).**
   - Limit 5 MB; check the PDF MIME type and magic bytes.
   - Celery task on queue `llm`; wait up to 15 s, then fall back to the rules result. Error `unreadable_pdf`.
   - Call AI's `llm_gateway.parse_resume`/`parse_jd` behind an import guard.
5. **Taxonomy (B23/G3).**
   - `manage.py sync_taxonomy` from `content/skills.yaml`.
   - Profile skills go through `normalize_skill()`. Return `unknown_skills` instead of creating rows, inside `atomic`.
   - `GET /api/taxonomy` reads `content/*.yaml`; topics come from the family registry.
6. **Identity.**
   - Send the verify-email link by SMTP outside `DEMO_MODE` (MailHog in compose).
   - B28 profile validation: salary range, and every `blocked_company_ids` entry exists.
7. **pgvector (A12)** once ML starts AI-11: a migration with `CREATE EXTENSION vector`, nullable `VectorField(1024)` on profiles and positions, and an HNSW index.
8. **`seed --mode=full` (BE-13).** Load `seed_data/full/*.jsonl` with `bulk_create` inside `atomic`, under 60 s. Agree the schema with ML first.
9. **BE-15 staging.** VPS, Caddy HTTPS, deploy from `main`, nightly `pg_dump`; `check --deploy` must be clean.
10. **P2 hygiene.**
    - GenericAPIView/ViewSets with scoped `get_queryset()`.
    - `@extend_schema_field` on every `SerializerMethodField`.
    - Enums instead of inline choices.
    - Make `AuditLog`/`OfferEvent` immutable.
    - Pinned `base.txt`/`dev.txt` requirements.
    - pre-commit with ruff.
    - Move from `authlib.jose` to `joserfc`.
    - Docs D1–D22.
11. **P2 features (TASKS.md):** BE-17 vacancies and applications, BE-18 micro-tasks, BE-19 anti-fraud, BE-20 contact revocation, floor warning and Need Health, BE-21 contacts encrypted at rest and PDF watermark, BE-23 Locust load test.

### 9.4 How to work (rules for the agent)

- **Branching:** pull `main` before each task. One branch and one PR per ID (e.g. `be/R5-visibility`), under ~400 lines, with the ID in the title.
- **TDD:** write the failing test first. API tests check the 401/403/404/409/422 boundaries.
- **Before every commit:** run `.venv/Scripts/python .claude/skills/verify/scripts/verify.py --full`. Regenerate `docs/openapi.json` in the same PR whenever the API changes.
- **Invariants (CLAUDE.md) are hard rules:**
  - contacts are read only via `ContactAccessService`
  - answer keys never leave the server
  - FSP never changes the grade
  - salary rules are enforced in both DB and DRF
  - every event payload carries `candidate_id` and/or `company_id`, or it reaches nobody
- **Migrations:** pull `main`, then run `makemigrations`. One migration per PR.
- **Errors:** no bare `except Exception` except at process boundaries, and then use `logger.exception`. Never raise inside an `atomic` block after writes you need to keep.
- **When finished:** tick the item here and in §8. We then review the whole batch with `django-reviewer`, `invariant-auditor` and `silent-failure-hunter`.
