# BE.md: Backend Tasks (owner: BIKHE)

> **Audience:** the backend developer (BIKHE) and their AI coding agent.
> **Scope:** all backend work that is not AI/ML: Django/DRF, data model, security, offers, consents, FSP linking, demo mode, deployment, CI, the API contract for the frontend, and the *wiring* of ML/LLM modules.
> **Stack:** Django 5.x + DRF, PostgreSQL (pgvector), Redis, Celery. Don't migrate to FastAPI.
> **Updated:** 2026-10-09, after PR #2 (`bikhe-p0-backend-fixes`) and the hotfix PR #4 (`fix/be-critical-hotfixes`), both merged. Earlier audits are in git history.
> **Start:** `git pull` on `main`, read §1 (what exists), then work through §3 in order.

---

## 0. Ownership and Boundaries

| File | Owner | Scope |
|---|---|---|
| **BE.md** | BIKHE, backend | Django apps, models, migrations, views, serializers, permissions, settings, Celery, OIDC mock, seed, deployment, CI, OpenAPI |
| [ML.md](ML.md) | ML engineer | Item families, CAT/IRT engine, grading math, matching scorer, Strength/FSP boost/percentile formulas, synthetic world, validation |
| [AI.md](AI.md) | AI / LLM engineer | LLM gateway, resume/JD parsing, PII redaction, skill taxonomy, "why" sentences |
| [FE1.md](FE1.md), [FE2.md](FE2.md) | Frontend | SPA in `web/`. They generate their client from `docs/openapi.json` |

**Rules**
1. **ML and AI code is pure:** no ORM, views or requests. You own everything that calls it: views, services, Celery tasks, persistence. **Don't edit the formulas** in `apps/assessment/engine.py` or `apps/matching/scoring.py`, or the item families. Edit only the adapters around them. Write a change request in ML.md or AI.md instead.
2. ML owns the engine signatures (ML.md §3) and AI owns the gateway signatures (AI.md §3). A signature change is one PR that touches both sides.
3. Every API change regenerates `docs/openapi.json` in the same PR.
4. **A9 (package layout):** apps import as top-level packages (`from assessment.models import ...`) because `config/settings.py` puts `apps/` on `sys.path`. Moving to `apps.<name>` needs coordination with ML and AI. Until then, don't add top-level names that clash with PyPI packages.

---

## 1. What Is Done

### 1.1 In place (PR #1 + PR #2)
- **Architecture:** a modular monolith with 7 apps plus `fsp_mock`. There is a services and selectors layer for assessment, FSP sync, profiles and matching. Errors use RFC 7807 problem+json with `errors: [{field, msg}]`. `docs/openapi.json` is real JSON and matches the code.
- **Settings:** `DEBUG` and `DEMO_MODE` are off by default. Startup fails fast without `SECRET_KEY` or `ALLOWED_HOSTS`. Auth is Session only, with `IsAuthenticated` as the default permission. `load_dotenv` is called. `.env.example` exists. `config/wsgi.py` and `config/asgi.py` exist.
- **Identity:** registration allows the candidate and employer roles only (B2). Demo personas are locked down (B3). `verify-email` exists, and the demo endpoints `time-travel` and `reset` exist. `GET /api/auth/csrf` exists.
- **Companies:** auto-creation is gone (B1). `POST`/`GET /api/companies` exist, and a user without a company gets `company_required`.
- **Privacy:** `visible_candidates_for` / `is_candidate_visible_to_company` use the latest consent (B4). The talent card returns 404 when the candidate is not visible (B5). Contacts are read only through `ContactAccessService` in `outreach/services.py`; `core/services.py` is a re-export shim. The PDF escapes its input and fetches only `data:` URLs (B6).
- **Strength (B10):** `base_strength` and `fsp_boost` are stored separately. `recompute_strength` recomputes from scratch, so it is idempotent.
- **Offers:**
  - `CreateOfferSerializer` computes `why_you` and `match_snapshot` on the server.
  - `version` is required.
  - `decline_reason` must be a `DeclineReason`.
  - interview, hired and close actions exist.
  - Contacts depend on the grant, not on the status.
  - The `expire_offers` beat task exists.
- **Other:** idempotent seed. Consents API. G2–G17 endpoints (see §2.3). Docker, Makefile, CI workflow and `pyproject.toml` (ruff).

### 1.2 Fixed by the hotfix PR #4 (critical bugs from the PR #2 review)
| ID | Was | Now |
|---|---|---|
| H1 | Anyone could log in as any FSP-linked user. The mock IdP was mounted in prod, and a failed token exchange made the client sign its own id_token. | The mock IdP and registry return 404 unless `DEMO_MODE`. PKCE is mandatory, and `redirect_uri` must be our callback. `identity/oidc.py` has no fallback: an IdP error gives 400 `token_exchange_failed` or 502 `fsp_id_unavailable`. The id_token is verified against the IdP JWKS: RS256, plus `iss`, `aud`, `exp` and `nonce` (nonce is also compared explicitly). `state` is single-use. `Identity.subject` is the IdP `sub`. An existing account is never matched by email (409 `account_exists`). The email counts as verified only if `email_verified` is true. User creation is atomic. The mock signing key is shared by all workers (`FSP_MOCK_PRIVATE_KEY_PEM`, or `var/fsp_mock_rsa.pem`). New setting `OIDC_INTERNAL_URL`. |
| H2 | `POST /api/fsp/link` accepted any participant ID (B7) | 403 `fsp_oidc_required` outside `DEMO_MODE`. Linking goes through OIDC `intent=link`. |
| H3 | A position could be moved to another company (B9) | `Position.company` is read-only and is set from the caller's membership |
| H4 | The SPA couldn't read the CSRF cookie | `CSRF_COOKIE_HTTPONLY = False` |
| H5 | A late answer rolled back finalize, and the session stayed stuck for 24 h | The deadline is set when an item is served. A late answer (past deadline + 3 s) counts as incorrect and the test continues. Items not yet served have `deadline_at = null`. |
| H6 | Instant fallback gave a grade with zero evidence, and short_test could be repeated without limit | Instant is allowed only if the session's own answers support the lower grade (409 `fallback_not_eligible`). short_test works once (409 `fallback_already_used`). The result's `fallback` hint uses the same check (`AssessmentService.fallback_offer`). |
| H7 | Concurrent starts created duplicate sessions | Partial unique constraint `uq_one_in_progress_assessment_per_spec` (migration `assessment/0004`) |
| H8 | SSE sent every tenant's events to every user | The audience comes from the payload: `candidate_id` equals the user, or `company_id` is one of the user's companies. It fails closed, replay is scoped, and dispatch happens in `transaction.on_commit`. |
| H9 | Lazy offer expiry was rolled back, and offers past `expires_at` were frozen | Expiry applies only to sent/viewed offers. It is persisted (with `OfferEvent` and `AuditLog`) before the 409 `offer_expired`. |

Tests for these are in `tests/test_security_hotfixes.py`, `test_assessment_lifecycle.py` and `test_sse_and_expiry.py`. The OIDC tests go through the real token endpoint (they patch `identity.oidc._http_post_form` and `_http_get_json`). Keep them green.

---

## 2. Contracts

### 2.1 ML boundary (see [ML.md](ML.md))
| Concern | ML delivers (pure) | You deliver (Django) |
|---|---|---|
| Item families | `apps/assessment/families/` registry, `make_rng()` | `manage.py sync_families`, which upserts `ItemFamily` rows (task N2) |
| CAT/IRT | `CatEngine.start / next_family / record / result`, `CatState.to_json() / from_json()` | Engine adapter (N2): persist `CatState`, serve one item at a time, deadlines, finish/abandon/fallback, cooldowns, league update |
| Matching | `score_pool(need, pool, weights)`, the `CandidateCtx`/`NeedCtx` DTOs | SQL prefilter, one batched load into DTOs, pagination, facets (N1) |
| Strength / boost / percentiles | `strength()`, `fsp_boost()`, `percentiles()` | `recompute_league(spec, grade)` after finalize and after FSP sync, idempotent (N3) |
| Synthetic world | `seed_data/full/*.jsonl` plus a schema README; registry data | `seed --mode=full` (N8); `fsp_mock` serves the registry |
| Validation report | `validation/out/report.json` | `GET /api/lab/report` (done; see R21) |

Until ML ships, the current stub stays behind the adapter, so the API shape doesn't change when the real engine lands.

### 2.2 AI / LLM boundary (see [AI.md](AI.md))
| Concern | AI delivers | You deliver |
|---|---|---|
| Resume parse | `llm_gateway.parse_resume(pdf_bytes)` with a rules fallback | `POST /api/candidates/me/resume`: up to 5 MB, PDF MIME, Celery queue `llm`, wait up to 15 s then return the rules result, error `unreadable_pdf` (N4) |
| JD parse | `llm_gateway.parse_jd(text)` | `POST /api/positions/parse`, same pattern (N4) |
| Taxonomy | `content/skills.yaml`, `taxonomy.normalize_skill(raw)` | `manage.py sync_taxonomy`. Never create `Skill` rows from user input (N5) |
| "Why" sentence | `llm_gateway.phrase(facts)` | Call it when creating an offer and store the result next to `why_you` |
| Settings | Reads `LLM_PROVIDER`, `GIGACHAT_*` | Env vars in settings and `.env.example`; Redis `CACHES` (R1) |

### 2.3 Frontend contract (G-IDs are referenced by FE1.md and FE2.md)
| # | Contract | Status |
|---|---|---|
| G1 | `GET /api/auth/csrf`; the SPA sends `X-CSRFToken` | ✅ (H4) |
| G2 | `POST /api/auth/verify-email`; `verify_link` in DEMO_MODE | ✅ in DEMO_MODE. Real email sending: N6 |
| G3 | `GET /api/taxonomy` | ⚠️ hard-coded; load it from content files (N5) |
| G4 | `POST /api/demo/reset` | ⚠️ resets only the clock (R17) |
| G5 | Assessment `finish`, `fallback`, ItemView and result fields | ✅ (H5, H6). The adaptive engine waits on ML (N2) |
| G6 | `POST /api/positions/parse` | ⚠️ stub (N4) |
| G7 | `GET /api/leagues` | ✅ |
| G8 | Pool/search params, facets, `components[]`, `gaps[]` | ⚠️ works, but has N+1 queries and no SQL filters (N1, R18) |
| G9 | TalentShort/TalentCard fields | ✅ (R8 for internal IDs) |
| G10 | The employer offer view has `talent` and `decline` | ✅ |
| G11 | `GET /api/lab/report` | ✅ (R21) |
| G12 | SSE `offer.*`, `league.updated`, `fsp.synced` | ⚠️ scoped (H8); cross-process transport: R24 |
| G13 | One error shape `[{field, msg}]` (B18) | ✅ |
| G14 | Pagination `{items,total,page,pages}` | ✅ |
| G15 | OIDC `fsp-id/login`, `callback` | ✅ (H1) |
| G16 | `GET /api/positions/{id}/shortlist` | ✅ (R5 visibility) |
| G17 | `POST`/`GET /api/companies` | ✅ (R20) |

**Error codes added by the hotfix** (FE must handle them): `offer_expired`, `fallback_not_eligible`, `fallback_already_used`, `account_exists`, `fsp_oidc_required`, `fsp_id_unavailable`.

### 2.4 Requests from other streams
ML, AI and FE add a row here when they need a model, endpoint or contract change. BE picks requests up as tasks.

| From | Request | Status |
|---|---|---|
| ML-0 | **Engine contract is published** (ML.md §3). `apps/assessment/engine.py` is now the package `apps/assessment/engine/`; `from assessment.engine import FAMILIES_REGISTRY, score_assessment` still works through `engine/legacy.py` until N2 lands, then ML deletes it. Wire through your adapters, never import ML internals elsewhere: `assessment.engine.cat` (`CatEngine`, `CatState.to_json/from_json`, `CatResult`, `item_level`), `assessment.families.registry` (`all_families`, `active_metas`, `make_rng`), `matching.engine.score` (`score_pool`, `passes_hard_filters`, `preset`), `matching.engine.types` (DTOs), `matching.engine.strength` (`strength`, `percentiles`, `fsp_boost`). Two optional fields were added with defaults: `CatState.seen` and `CandidateCtx.microtask_dates`. | open |
| ML-2 | **Taxonomy from content files** (G3/N5): `GET /api/taxonomy` should read `assessment.engine.content.load_content()` (validated, cached): `grades` → `[{id, name_ru, descriptor_ru, theta_cut, rating_cut}]`, `specializations`, and topics → `[{id, name_ru, specs, skills}]`. Topic ids are what `CatResult.topics` and JD blueprints use. Skill names come from AI's `skills.yaml`. Grade cuts are now −1/0/+1 (D7 in ML.md §8); FE copy should use `descriptor_ru`. | open |
| ML-5 | **Lab report (R21):** `validation/out/report.fixture.json` exists (`synthetic_fixture: true`), and ML-8 writes a real `report.json`. `LabReportView` should validate with `validation.schema.validate_report` (pure) and answer a logged 500 `report_unreadable` on errors, instead of `except Exception: pass` and the hard-coded metrics fallback, which shows invented numbers to the jury. | open |
| ML-4 | **Matching and Strength wiring (N1, N3, B10).** *Pool:* SQL prefilter as in `passes_hard_filters` (spec, grade or adjacent if `allow_adjacent`, overlapping `work_formats`), then one batched load into `CandidateCtx` (`skills` as `SkillEvidence(skill_id, source, level=1.0)` by **skill id**; `topic_levels` from the latest finished session's `topics`; `fsp_rank`, `fsp_results`; `microtask_dates` = accepted micro-task dates or `()`; `strength`/`percentile` as stored) → `score_pool(need, ctxs, preset(position.preset) or Weights(**position.weights), now)`. `PoolItem.components/reasons/gaps` map 1:1 to `Scored`. Retire `matching/scoring.py` (`calculate_match_score`) in the same PR, and build `why_you` in offers from `Scored.reasons`. *League (N3):* `recompute_league(spec, grade)` = θ of all members → `strength(c, thetas, now)` per member → store `base_strength = base`, `fsp_boost`, `strength = total`, `percentile`. Call it after finalize and after FSP sync, and replace `recompute_strength`'s `min(15, 5·n)` with `fsp_boost(rank, results, now)` (idempotent, so the B10 storage stays valid). *Test evidence:* after finalize, upsert `CandidateSkill(source='test')` for `verified_skills(result.topics, state.administered, {m.id: m.skills for m in metas})`. | open |
| ML-3 | **Swap in the CAT engine (N2), gated on ML-6.** Today `active_metas(spec)` has 2–3 families, so every real session would end `pool_exhausted` after a few items and be unconfirmed. `tests/ml/test_cat.py::test_registry_is_big_enough_for_a_full_cat` is a strict xfail that flips when the pool is big enough (≥ 20 families per spec covering every topic); wire after that. Wiring via `assessment/engine_adapter.py`: start → `IrtCatEngine().start(spec, claimed, mode, kind, active_metas(spec), seen=<family ids served to this candidate in earlier sessions>)` and store `state.to_json()` in `AssessmentSession.state`; serve → `meta = engine.next_family(state, active_metas(spec), make_rng(settings.ITEM_SEED_SECRET, str(session.id), 'select', len(state.administered) + 1))`, then `inst = all_families()[meta.id].generate(make_rng(secret, str(session.id), meta.id, seq))` where `seq = state.administered[-1]['seq']`; store `inst.view()`, `inst.key`, `inst.fingerprint`; `ItemView.level = item_level(meta)`, `max_items = state.max_items`, `time_limit_s = meta.time_limit_s`, and persist the state (next_family appends a pending entry and is safe to call again); answer → `family.is_correct(item.key, {'option_id': ...} or {'value': ...})` (never `==`; typed answers normalise), then `engine.record(state, meta.id, correct, late=<past deadline>)` and `next_family`; `None` ⇒ finalize; finalize/finish/abandon → `engine.result(state)` (pure and order-independent; `result.complete` tells a finished test from an ended one, D8). Store theta, se, rating, rating_ci, result_grade (the achieved band, R10), decision, promotion_unlocked, fallback_grade, topics, evidence. A session ended by finish/abandon is never `confirmed` (D8), so H6's instant-fallback check can read `result.fallback_grade` instead of re-scoring. Then delete the legacy `FAMILIES_REGISTRY`/`score_assessment` path; ML removes `engine/legacy.py`. **Until this lands, live grading is still the legacy formula** (θ = mean b + …, cuts −1/−0.2/0.6/1.5), which BE's lifecycle tests pin. | open |
| ML-1 | **CI for item families** (R25): add `actions/setup-node` (Node ≥ 20) to `.github/workflows/ci.yml`, set `CI=true` (the real-Node event-loop test fails instead of skipping when `CI` is set), and add a step `cd apps && python -m assessment.families.verify --n 1000` (about 70 s today; exit 1 blocks the merge). **`sync_families` (N2) must upsert** `a`, `b`, `c`, `topic`, `format`, `time_limit_s` from `active_metas(spec)`: `services.py` currently `get_or_create`s rows with the legacy values (format `'choice'`, b from the legacy adapter), which never update. The legacy registry now serves the fixed v2 families (keys are random option ids, ML-F1 closed). It keeps the old b/time limits only because `test_assessment_lifecycle.py` pins the legacy scorer's numbers. | open |

---

## 3. Tasks (in this order)

Each task gets a failing test first, then the fix. Tick a box when its PR is merged.

### 3.1 Rework from the PR #2 review: do these first

**Security and privacy**
- [ ] **R1. Throttles are configured but not attached.**
  - Set `throttle_scope`: `login` on `LoginView`, `register` on `RegisterView`, and `fsp_sync` on `FSPLinkView` and `FSPSyncTaskTriggerView`.
  - Set `offers` on `OfferListCreateView` for POST only (override `get_throttles`).
  - Set `resume` on `ResumeParseView`; `PositionParseView` gets its own `jd_parse`.
  - Add `CACHES` = `RedisCache(REDIS_URL)` so limits are shared across workers, and set `NUM_PROXIES` from env.
  - Test: the (N+1)-th login gets 429 with `Retry-After`.
- [ ] **R2. Secrets.**
  - `ITEM_SEED_SECRET` fails fast when `DEBUG=False`, as `SECRET_KEY` does. Remove the fallback in `assessment/services.py`.
  - Remove the `SECRET_KEY` and `ITEM_SEED_SECRET` defaults from `docker-compose.yml` (use `env_file`).
  - Add `OIDC_INTERNAL_URL` and `FSP_MOCK_PRIVATE_KEY_PEM` to `.env.example`.
  - Add a system check that warns when `DEMO_MODE and not DEBUG`. In DEMO_MODE the mock IdP lets anyone log in as any FSP participant, so a demo host must never hold real users.
- [ ] **R3. Admin leaks.**
  - `AssessmentItemAdmin`: exclude `key`, `fingerprint` and `seed`; no add or change.
  - Unregister the `CandidateContact` admin.
  - `LeagueMembership`, `AssessmentSession`, `AuditLog`, `OfferEvent` and `ContactGrant` admins become read-only.
- [ ] **R4. Contact reads.**
  - Talent card: catch only `ContactNotGranted`, not `Exception`.
  - `OfferSerializer.get_candidate_contacts`: call `has_active_grant()` first and `get_contacts()` only when granted. Today `GET /offers` writes N false-denial `AuditLog` rows.
- [ ] **R5. Visibility.**
  - One rule in `profiles/selectors.py`, shared by the queryset and `is_candidate_visible_to_company`:
    - the latest publication consent is granted
    - `open_to_offers` is set
    - the email is verified
    - at least one non-pending league exists (`Exists(...)`)
    - the blocklist is applied in SQL: `~Q(blocked_company_ids__contains=[company.id])`
    - ordering is `order_by(..., 'id')`
  - Shortlist `PUT` and `POST /offers` return the same 404 for invisible and nonexistent candidates.
  - Test: after revoking publication consent, the candidate is gone from pool, search, card, shortlist and offer.
- [ ] **R6. Login CSRF.** DRF doesn't CSRF-check anonymous `login`, `register` or `demo/persona`; add `@method_decorator(csrf_protect)`. Test with `APIClient(enforce_csrf_checks=True)`.
- [ ] **R7. PDF.** Return 503 on `ImportError` too, not HTML named `.pdf`. Add a malicious-skill test (`<img src="file:///etc/passwd">`, `http://169.254.169.254/`).
- [ ] **R8. No internal UUIDs in employer-facing payloads.**
  - Talent-card assessment IDs and the `candidate_id` in SSE events sent to employers become `public_id`.
  - Non-blind `display_name` shows `full_name`: confirm with product.

**Assessment and data integrity**
- [ ] **R9. A failed promotion or abandon overwrites a confirmed grade** (`finalize_assessment`).
  - If the league is CONFIRMED at grade G, a failed higher claim keeps G and CONFIRMED. The attempt is stored on the session only.
  - Clear `confirmed_at` whenever the status becomes unconfirmed.
  - `/verify` never returns `valid: true` for unconfirmed.
- [ ] **R10.** An unconfirmed session stores `result_grade = claimed_grade`. Store the scorer's achieved grade instead, and show `decision` next to it on the talent card.
- [ ] **R11. Abandon and stale rules (ARCHITECTURE §2.5).**
  - `/finish` and the stale-session sweep count as an attempt (finalize unconfirmed plus cooldown) only if at least 50% of items were answered. Otherwise the session becomes `ABANDONED`/`EXPIRED` with no cooldown.
  - Use `AssessmentStatus.ABANDONED`.
  - `EligibilityView` checks in-progress sessions per specialization.
- [ ] **R12. Request validation.**
  - `StartAssessmentSerializer`: required fields, and `mode` from `AssessmentMode.choices` (today `'trial'` doesn't match `'express'`).
  - `AnswerRequestSerializer.validate()` requires `option_id` or `value`.
  - The short-test session gets `kind=FALLBACK, counts_as_attempt=False`.
  - The instant-fallback membership `get_or_create` derives `base_strength` from θ, as `finalize_assessment` does.
- [ ] **R13.** `GET /assessments` shows `evidence[].correct` while a session is in progress. Show it only when finished.
- [ ] **R14. FSP sync (`fsp_sync/services.py`).**
  - Wrap `sync_fsp_data` in `atomic`.
  - On a registry miss, set `sync_status` to `NOT_FOUND`/`FAILED` and keep the old results.
  - Delete results the registry no longer returns.
  - Replace the `base==0 and strength>0` backfill with a one-off data migration, and delete the tautological grade check.
  - `sync_all_fsp_profiles`: `autoretry_for`, `logger.exception` with the IDs, return `{ok, failed}`. Either put it in `CELERY_BEAT_SCHEDULE` or delete it.
- [ ] **R15. Offers.**
  - `expire_offers` reuses `OfferService._expire_locked` (for the `AuditLog`) and isolates per-row failures.
  - Consent revoke (`profiles/views.py`): catch `InvalidTransition`, `OfferExpired` and `VersionConflict` explicitly. Retry `VersionConflict` once with a fresh version. Use `logger.exception`.
  - Document 409 `offer_expired` in `extend_schema`.
  - `CooldownActive` sends `Retry-After`.
- [ ] **R16. Salary (invariant 5, B15).**
  - `salary_invalid` for every salary error on position create/update and on offer create.
  - Add a DB `CheckConstraint` `salary_type IN ('gross','net')` on Position and Offer.
  - API tests: `salary_min=0` gives 422 on create and on update.
- [ ] **R17. Demo.**
  - Time travel only for `is_demo` users, and it sets the offset (no `+=`).
  - `/demo/reset` restores the persona's seeded data, not just the clock.
- [ ] **R18.** Pool and search take `page >= 1` and `1 <= size <= 100` through a serializer; anything else is 422 (`size=0` is a 500 today).
- [ ] **R19.** `public_id` has at least 8 hex characters, with retry on collision. Every `LeagueMembership` `.first()` filters by specialization or relies on `Meta.ordering`.
- [ ] **R20. Companies.**
  - `UniqueConstraint` on `CompanyMember.user`, since the `exists()` check races.
  - `GET /api/companies` requires `search` of at least 2 characters and is paginated.
  - Handle the admin branch of `GET /offers` explicitly.
- [ ] **R21. No fake data.**
  - A corrupt `report.json` gives a logged 500 `report_unreadable`, never hard-coded metrics.
  - The resume stub returns `source='stub'` with empty skills until AI's `parse_resume` lands.
- [ ] **R22. Small fixes.**
  - `EventStreamRenderer` renders error dicts as JSON.
  - Concurrent first FSP logins for the same participant give `IntegrityError` → 409, not 500.
  - Reversing migration `assessment/0004` breaks once items have `deadline_at = NULL`: backfill in the reverse function, or document it as irreversible.

**Infra and CI**
- [ ] **R23. Compose is broken.**
  - `worker`, `worker-llm` and `beat` crash because `ALLOWED_HOSTS` is missing. Share one env anchor `x-backend-env: &backend-env` across all Python services.
  - The local stack is HTTP-only. `api` already has `SECURE_SSL_REDIRECT=False` (needed for the IdP self-call); move it into the shared env. Make `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` env-configurable, otherwise the browser drops cookies and login fails.
  - Decouple HSTS and `SECURE_PROXY_SSL_HEADER` from the redirect flag.
  - Remove `seed || true` from the entrypoint.
  - Add `.gitattributes` with `*.sh text eol=lf`.
  - Done means: `docker compose up --build`, then log in with FSP ID in a browser.
- [ ] **R24. SSE transport.**
  - Add a Redis subscriber on channel `fsp_events`, so events from other workers and from Celery arrive.
  - Serve `/api/events` from an ASGI worker (uvicorn) or a separate service, so streams don't pin sync gunicorn workers.
  - Send a keepalive every 15 s.
  - If this isn't done by the demo, return 501 and FE keeps polling.
- [ ] **R25. CI.**
  - Run on every PR and push.
  - `pytest --cov=apps --cov-fail-under=75`.
  - OpenAPI drift check: regenerate, then `git diff --exit-code docs/openapi.json`.
  - Python 3.13.
  - One pytest config with `testpaths=["tests"]`.
  - Add `LOGGING` (console, INFO).
  - Fix the 6 drf-spectacular warnings (`ENUM_NAME_OVERRIDES`, duplicate operationIds).
- [ ] **R26. Missing tests:**
  - wsgi import smoke
  - `role=admin` register gives 400
  - persona: off outside DEMO_MODE, unknown persona gives 422, non-demo user is rejected
  - two employers with the same email local part
  - `company_required` gives 403
  - invisible talent card gives 404, plus an `AuditLog` row
- [ ] **Docs.** AGENTS.md, ARCHITECTURE.md and the README must say that contact gating lives in `outreach/services.py`. Add the new error codes to the README catalog.

### 3.2 Remaining backend work: after 3.1

- [ ] **N1. Pool and search rewrite** in `matching/services.py` + `selectors.py`.
  - SQL hard filters: specialization, grade adjacency, `work_formats`, `salary_max`.
  - One batched query (`select_related`/`prefetch_related`), turned into DTO dicts and passed to the scorer.
  - Pagination and facets in SQL.
  - Tests: `django_assert_max_num_queries(15)`, and p95 < 300 ms on 1,500 candidates.
- [ ] **N2. Engine adapter.** Create `assessment/engine_adapter.py` with the ML.md §3 interface (`start`, `next_item`, `record`, `result`, `CatState.to_json`), backed by the current stub. Services call only the adapter.
  - Add `manage.py sync_families` and stop the lazy `ItemFamily` `get_or_create(format='choice')`.
  - When ML ships `CatEngine`, swap it in inside the adapter.
- [ ] **N3. `recompute_league(spec, grade)`** via the adapter (stub: rank-based percentile).
  - Trigger it after finalize and after FSP sync, and emit `league.updated`.
  - Idempotency test.
- [ ] **N4. Resume and JD.**
  - Limit 5 MB; check the PDF MIME type and magic bytes.
  - Celery task on queue `llm`; wait up to 15 s, then fall back to the rules result. Error `unreadable_pdf`.
  - Call `llm_gateway.parse_resume`/`parse_jd` behind an import guard until AI ships them.
- [ ] **N5. Taxonomy.**
  - `manage.py sync_taxonomy` from `content/skills.yaml`.
  - Profile skills go through `normalize_skill()`. Return `unknown_skills` instead of creating rows, inside `atomic`.
  - `GET /api/taxonomy` reads `content/*.yaml`; topics come from the family registry.
- [ ] **N6. Identity.**
  - Send the verify-email link by SMTP outside DEMO_MODE (MailHog in compose).
  - Profile validation: the salary range, and every `blocked_company_ids` entry exists.
- [ ] **N7. pgvector** once ML starts embeddings (AI-11): a migration with `CREATE EXTENSION vector`, nullable `VectorField(1024)` on profiles and positions, and an HNSW index.
- [ ] **N8. `seed --mode=full` (BE-13).** Load `seed_data/full/*.jsonl` with `bulk_create` inside `atomic`, under 60 s. Agree the schema with ML first.
- [ ] **N9. Staging (BE-15).** VPS, Caddy HTTPS, deploy from `main`, nightly `pg_dump`; `check --deploy` must be clean.
- [ ] **N10. Hygiene.**
  - GenericAPIView/ViewSets with scoped `get_queryset()`.
  - `@extend_schema_field` on every `SerializerMethodField`.
  - Enums instead of inline choices.
  - Make `AuditLog`/`OfferEvent` immutable.
  - Pinned `base.txt`/`dev.txt` requirements.
  - pre-commit with ruff.
  - Move from `authlib.jose` to `joserfc`.
  - Update README, ARCHITECTURE and TASKS to match the code.
- [ ] **N11. Product features (TASKS.md):** BE-17 vacancies and applications, BE-18 micro-tasks, BE-19 anti-fraud, BE-20 contact revocation, floor warning and Need Health, BE-21 contacts encrypted at rest and PDF watermark, BE-23 Locust load test.

---

## 4. How to Work (rules for the agent)

- **Branching:** pull `main` before each task. One branch and one PR per ID (e.g. `be/R5-visibility`), under ~400 lines, with the ID in the title.
- **TDD:** write the failing test first. API tests check the 401/403/404/409/422 boundaries.
- **Before every commit:** run `.venv/Scripts/python .claude/skills/verify/scripts/verify.py --full` (ruff, check, `makemigrations --check`, pytest, invariant scan). Regenerate `docs/openapi.json` whenever the API changes. The local DB is described in `CLAUDE.md`.
- **Invariants (`CLAUDE.md`) are hard rules:**
  - contacts are read only via `ContactAccessService`
  - answer keys and fingerprints never leave the server
  - FSP never changes the grade
  - salary rules are enforced in both DB and DRF
  - every domain event payload carries `candidate_id` and/or `company_id`, or it reaches nobody
- **Migrations:** pull `main`, then run `makemigrations`. Don't number them by hand. One migration per PR.
- **Errors:**
  - No bare `except Exception` except at process boundaries, and then use `logger.exception`.
  - Never raise inside an `atomic` block after writes you need to keep.
  - Publish events with `publish_domain_event` (it already runs on commit).
- **When finished:** tick the task here. After the batch, we review with the `django-reviewer`, `invariant-auditor` and `silent-failure-hunter` agents.
