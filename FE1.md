# FE1.md: Frontend Dev 1 — Rework, Merge, then all P1 frontend work

> **Audience:** frontend developer 1 and their AI coding agent.
> **Date:** 2026-10-09. Related files: [FE2.md](FE2.md), [BE.md](BE.md) (backend status and gaps G1–G17), [ML.md](ML.md), [AI.md](AI.md), `docs/TASKS.md` §2.6 (task IDs).
> **Scope change (2026-10-09):** FE1 now owns **every P1 frontend task** (FE-13 … FE-19). FE2 keeps its five P0 tasks only (FE-05, FE-09, FE-10, FE-11, FE-12; see FE2.md).
>
> **Order of work:** §2 Rework → merge `fe1-p0-tasks` → tell FE2 → §3 P1 tasks in the order given there.

---

## 0. Ground rules (unchanged, short)

- **Product:** candidates take one adaptive test and land in a League (specialization × grade, confirmed or unconfirmed). Employers browse ranked, explained pools and send Draft Offers with a mandatory salary range (RUB/month, gross or net). **Contacts stay hidden until the candidate accepts.** FSP achievements change ranking, never the grade.
- **UI language: Russian.** Code, comments, identifiers: English.
- **UX rules:** one primary action per screen; **salary and status always visible**; **verified (`test`, `fsp`) and declared data look different** (solid border + label vs dashed border, see `ReasonChips`/`SkillChip`); WCAG AA; loading, empty and error states on every screen.
- **Score explainability:** every match score shows reason chips, and the contributions shown sum to the score shown. Never render a score without its breakdown.
- **Conventions (as built, after R5):** hooks live in `src/api/<feature>.ts` and call `customFetch`; types come from `@/api/types` (derived from `@/api/generated/models`; hand-written only for gaps, each marked `// gap Gx`); query keys from `@/api/keys`; mocks in `src/mocks/handlers/<feature>.ts` with header `X-Stub: true`; enum → Russian text only through `lib/labels.ts`; error code → Russian text only through `i18n/errors.ts`.
- **Process:** one commit per item, message prefixed with the ID (`R18 …`, `FE-13 …`). One PR per task ID, under ~400 lines, reviewed by FE2. Every PR description pastes the output of `pnpm typecheck && pnpm lint && pnpm test && pnpm build`.

---

## 1. Status (review of `fe1-p0-tasks` @ `3e7baa2`, 2026-10-09)

Verified in a clean worktree: `typecheck` ✅, `lint` ✅, `test` ✅ 23/23, `build` ✅ (only after deleting the `packageManager` field, see R18). Not merged: `main` has no `web/` yet.

| Task | Result |
|---|---|
| F-06 Web skeleton | ✅ |
| FE-01 Tokens & domain components | ✅ (palette is "Arena (dark)", lead decision pending) |
| FE-02 Shell, auth, live updates | ✅, small gaps in R20, R21 |
| FE-03 Jury Mode | ✅ public, anonymous `/` → `/jury` |
| FE-04 Onboarding | ✅ prefill hydrates after load |
| FE-06 Result & history | ✅ (switch to real G5 fields, R24) |
| FE-07 Dashboard & offers | ✅, auto-view hang left (R19) |
| FE-08 Settings | ✅ (FSP link must follow G15, R26) |
| Rework R1–R15 | ✅ except the R1 `packageManager` part (→ R18) and part of R10 (→ R19) |
| R16 PR, R17 notify FE2 | ❌ open |

Quality is good: one commit per item, clean guard extraction with tests, stateful offer mocks with versioning and 409s. What remains is below.

---

## 2. Rework before merge (branch `fe1-p0-tasks`)

All paths relative to `web/`. Fix in order; one commit per item.

### Blockers

- [x] **R18 · Clean clone still fails.** `package.json` keeps `"packageManager": "pnpm@12.10.1"`; pnpm 11 cannot bootstrap it and every script fails before install.
  - **Fix:** pin the version the team actually runs (`pnpm -v`, today `11.11.0`) or delete the field.
  - **Acceptance:** in a fresh directory `git clone … && cd web && pnpm install --frozen-lockfile && pnpm typecheck && pnpm lint && pnpm test && pnpm build` is green with no manual edits. Paste the output into the PR.

- [x] **R19 · Offer auto-view can still hang (rest of R10).** `features/offers/offer-detail-page.tsx` retries `POST /view` only when the `offer` object changes. If the refetch returns identical data (lazy expiry after time travel: GET says `sent`, POST says `invalid_transition` / `offer_expired`), TanStack keeps the same reference, the effect never re-runs, and the page shows "Открываем оффер…" forever.
  - **Fix:** in the conflict branch, `const { data } = await refetch()`; if `data?.status === 'sent'` and no retry was made yet, call `view.mutate` directly with `data.version`; otherwise do nothing (the status moved on). Any second failure, and `offer_expired`, sets `viewError` (shows `ErrorState`).
  - **Acceptance:** a Vitest test with MSW: `/view` returns 409 twice and GET returns the same body → `ErrorState` with a retry button renders, no endless "Открываем оффер…".

### Correctness

- [x] **R20 · Login ignores `?next=`.** The 401 handler sends users to `/login?next=<path>`, but `features/auth/login-page.tsx` always navigates to `/`.
  - **Fix:** after login, navigate to `next` if it starts with `/` and not `//` (no open redirect) and matches the user's role area; otherwise `/`.
  - **Acceptance:** delete the `sessionid` cookie on `/candidate/offers/<id>` → land on `/login` → log in → back on the same offer.

- [x] **R21 · 401 handling sends duplicate requests and toasts.** `app/providers.tsx` uses the default `retry: 1`, so every 401 is retried once before the redirect, and parallel 401s each fire a toast and a navigation.
  - **Fix:** `retry: (n, e) => !(e instanceof ApiError && (e.status === 401 || e.status === 403)) && n < 1`; `toast.error(…, { id: 'session-expired' })`; skip `navigate` if a redirect to `/login` is already pending.
  - **Acceptance:** on `/candidate` with a dead session, the network tab shows each query once, and there is exactly one toast.

- [x] **R22 · `all`-mode mock skips the qualification gate.** `mocks/handlers/core.ts` (`PUT /api/candidates/me`) sets `onboarding_step = 'done'` as soon as `claimed_grade` is saved. The backend keeps `qualification` until a test finishes (`apps/identity/views.py:151`), which is exactly the state R2 was about.
  - **Fix:** claim keeps `qualification`; the mocked `POST /api/assessments/:id/finish` (all mode) sets `done`.
  - **Acceptance:** in `all` mode, after the claim step, `/candidate` redirects to `/candidate/qualification/start`.

### Sync with the backend (BE closed most gaps on 2026-10-08/09, see BE.md §2.3)

- [x] **R23 · Regenerate the schema.** `openapi/schema.json` is from 2026-10-08 22:56, and `docs/openapi.json` changed on 2026-10-09. Run `pnpm api:schema && pnpm api:gen`, then fix `src/api/types.ts` and anything that no longer typechecks.
- [x] **R24 · `missing` mode must mock only what is still missing.** These are now real on the backend: G1 `GET /api/auth/csrf`, G2 `POST /api/auth/verify-email`, G3 `GET /api/taxonomy` (hard-coded but live), G4 `POST /api/demo/reset` (clock only), G5 `POST /api/assessments/:id/finish` and result fields, G6 `POST /api/positions/parse` (stub but live), G7 `GET /api/leagues`, G11 `GET /api/lab/report`. Remove them from `gapHandlers` / `demoGapHandlers` in `missing` mode (keep them for `all`).
  - The result page now gets real `rating_ci`, `percentile`, `topics`, `evidence`, `fallback`, `next_attempt_at` (check the regenerated types; hide a section only when the field is truly absent).
  - `GET /api/assessments` is paginated `{items,total,page,pages}` (G14); keep accepting a bare array.
  - **Acceptance:** with `VITE_API_MOCKS=missing` and the live backend, no response on persona → onboarding → result → offers → settings carries `X-Stub`.
- [x] **R25 · New error codes.** Add Russian texts to `i18n/errors.ts` for `offer_expired`, `fallback_not_eligible`, `fallback_already_used`, `account_exists`, `fsp_oidc_required`, `fsp_id_unavailable`. On the offer detail, `offer_expired` refetches and shows the expired state.
- [x] **R26 · FSP link follows G15.** Outside DEMO_MODE `POST /api/fsp/link` now returns **403 `fsp_oidc_required`** (`apps/fsp_sync/views.py:29`). In settings: if `me.demo`, keep the POST; otherwise (and on `fsp_oidc_required`) send the browser to `/api/auth/fsp-id/login?intent=link`. Check where `FspIdCallbackView` returns the user and show the outcome (linked / `fsp_id_unavailable` 502) on `/candidate/settings`.
- [x] **R27 · Real company picker for the blocklist.** G17 is done: replace the mocked picker in settings with `GET /api/companies` (search by name). Keep the read-only list.

### Cleanup

- [x] **R28 · No dead generated client.** `orval` with `client: 'fetch'` still emits `src/api/generated/fSPDraftAPI.ts` (1638 lines, imported nowhere). Either delete it in the `api:gen` script after generation, or add an ESLint `no-restricted-imports` rule for `@/api/generated/fSPDraftAPI` so nobody bypasses `customFetch` (CSRF, problem+json). Document the choice in `web/README.md`.
- [x] **R29 · Placeholder task IDs are wrong** in `app/router.tsx`. Use: qualification start and runner → `FE-05`; `/employer`, `/employer/company`, `/employer/positions/new` → `FE-09`; `/employer/positions/:id` → `FE-10`; `/employer/offers` → `FE-11`; `/employer/talent` → `FE-12`; `/lab` → `FE-13` (FE1).
- [x] **R30 · Code-split routes.** The main chunk is 899 KB (Vite warns at 500 KB). Lazy-load route pages with React Router `lazy`, plus `/dev/ui` and `/dev/design`. Target: main chunk < 400 KB. Needed before Recharts comes back in FE-13.

### Process

- [x] **R16 · Open the PR** `fe1-p0-tasks → main`, titled `FE1-0 FE-01..08 Scaffold and candidate screens`. Description: the §1 table, the R18 clean-clone output, screenshots of `/jury` (anonymous), onboarding, result (3 variants), offer detail, settings. **`FE1.md` conflicts with `main`** (this file was rewritten there): resolve by taking `main`'s version and ticking the R-items you finished.
- [ ] **R17 · After merge, tell FE2 the same hour.** They are blocked on `components/domain/`, `lib/labels`, `useCountdown`, the router and guards.

---

## 3. P1 tasks (all owned by FE1 now)

Start only after R16 is merged. Recommended order: **FE-18 (own screens) → FE-13 → FE-19 → FE-15 → FE-16 → FE-17 → FE-14**: first what is unblocked and visible to the jury, then what waits on BE/ML.

| ID | Size | Blocked by | Status of dependency (2026-10-09) |
|---|---|---|---|
| FE-13 Validation Lab | M | G11 | ✅ backend serves the report (fixture fallback) |
| FE-19 Playwright e2e | S | FE-05, FE-10, FE-11 (FE2); CI from BE | ❌ FE2 P0 not started |
| FE-15 Vacancies & applications | M | BE-17 | ❌ not started (BE.md N11), mock it |
| FE-16 Micro-tasks | M | BE-18 | ❌ not started (BE.md N11), mock it |
| FE-17 Pool power features | M | FE-10 (FE2), ML-10, BE-20 | ❌ mock it, build after FE-10 merges |
| FE-14 Test Twins & Blueprint Builder | S | BE-22, ML-12, AI-14 | ❌ mock it |
| FE-18 Polish | M | PD-05 copy; FE2's screens merged | partly unblocked |

- [x] **FE-13 · Validation Lab** (M), route `/lab` (public, inside `AppLayout`, no SSE for anonymous users). Folder `features/lab/`.
  - `GET /api/lab/report` → `ValidationReport` (shape: `docs/TASKS.md` §1.4, line ~372). The backend serves `validation/out/report.json`, else `report.fixture.json` with `synthetic_fixture: true`.
  - **Red "FIXTURE" banner whenever `synthetic_fixture` is true.** Fake numbers never reach the jury unlabeled.
  - Re-add `recharts` (it was removed in R13; it is now used here) and lazy-load the page. Charts: confusion-matrix heatmap; accuracy / QWK / retest KPI tiles; TIF line chart; leak-attack bars (static vs parametric); systems table with nDCG@10 and P@10 bars; non-FSP parity and pool p95. Show `generated_at` and `git_sha`.
  - Every chart has a text alternative (table or `aria-label`), and colours come from `tokens.css`.
  - *Done:* renders from the live backend and from an `all`-mode fixture; banner shows for the fixture; link from `/jury` works.

- [ ] **FE-19 · Playwright e2e** (S), `web/e2e/`. The golden path against the docker compose stack, two browser contexts:
  1. Persona login (candidate) → onboarding → test (FE2 runner) → result.
  2. Employer: pool → send offer.
  3. Candidate: offer appears (live or ≤ 10 s) → accept.
  4. Employer: contacts appear.
  - **Assert that no response carries `X-Stub`.** A script `pnpm e2e`; it runs in CI once BE adds the workflow (M1).
  - Until FE2's screens land, write steps 1 and 3 and mark the rest `test.fixme`.

- [x] **FE-15 · Vacancies & applications** (M). Depends on BE-17; mock it in its target shape until then and add a gap row to BE.md §2.3 if the contract is not written down yet.
  - **Candidate:** `/candidate/vacancies` (list with salary first, league fit, apply button), application statuses on the dashboard.
  - **Employer:** a publish toggle and an applicant pipeline on the position. The page `/employer/positions/:id` belongs to FE2 (FE-10): agree with FE2 on a tab/slot and build your part as components in `features/vacancies/`.
  - *Done:* apply → the employer sees the applicant → status change reaches the candidate.

- [ ] **FE-16 · Micro-tasks** (M). Depends on BE-18; mock it.
  - **Candidate:** a task inbox and a solve screen. **Employer:** create, review, and "invite from a submission" (creates a Draft Offer through FE2's send-offer modal).
  - A reviewed submission is evidence with source `microtask`: give it its own chip variant on `/dev/ui`, distinct from `declared`.
  - *Done:* create → solve → review → invite works end to end on mocks.

- [ ] **FE-17 · Pool power features** (M), on FE2's scouting page (`/employer/positions/:id`). Start after FE-10 is merged. Depends on ML-10 (relaxations, acceptance likelihood) and BE-20 (floor warning, Need Health); mock it.
  - Weight presets (balanced / skills / budget) and sliders that re-rank live. Re-ranked rows must still show contributions that sum to the shown score (use `normalizeComponents()`).
  - Counterfactual hints from `relaxations` ("убрать Kubernetes → +23 кандидата").
  - An acceptance-likelihood badge (low / medium / high) next to "Send".
  - A Need Health panel (decline analytics by reason).
  - A below-salary-floor warning in the send-offer modal before sending (do not reveal the floor value).
  - *Done:* all five render from fixtures; moving a slider reorders the pool without a request.

- [ ] **FE-14 · Test Twins & Blueprint Builder** (S). JD → blueprint → two unique test instances side by side with the same difficulty profile. Depends on BE-22 (`GET /api/lab/twins?position_id=`), ML-12 and AI-14; mock it. Lives under `/lab` (a "Test Twins" section) and as a link from the position page.
  - Never show answer keys: render only what `ItemView` exposes.
  - *Done:* two instances render from a fixture with matching difficulty bars.

- [ ] **FE-18 · Polish** (M), the whole app (FE2 fixes bugs you report on their screens; the polish pass is yours).
  - **Phones (375 px):** candidate screens, the test runner, the offers board and the send-offer modal (needed for the QR demo).
  - A contrast check of every token pair used as text (record the ratios in `tokens.css`, as in R7b).
  - Loading, empty and error states on every screen; a Russian copy pass (PD-05 copy for Jury Mode when it arrives).
  - *Done:* no horizontal scroll at 375 px on any route; an axe run on each route reports no contrast or label violations.

---

## 4. Coordination

- **With FE2:** FE2 owns FE-05, FE-09, FE-10, FE-11, FE-12 and their folders (`qualification-runner/`, `employer/`, `scouting/`, `talent/`, `offers-employer/`). FE1 owns the scaffold, `api/client.ts`, `api/events.ts`, router, guards, `components/domain/`, `features/lab/` and every P1 feature. When a P1 task touches an FE2 page (FE-15, FE-16, FE-17), agree on the extension point first and send the PR to FE2 for review. Shared components go to `components/domain/` with a `/dev/ui` entry.
- **With BE:** regenerate the client when `docs/openapi.json` changes. New needs go to BE.md §2.3 as gap rows. Your open dependencies: BE-17, BE-18, BE-20, BE-22, the CI workflow for FE-19, G3 (taxonomy from content), G4 (full reset), G12 (SSE across processes).
- **With ML:** `ValidationReport` semantics (FE-13), `relaxations` and acceptance likelihood (ML-10, FE-17), twins/blueprints (ML-12, FE-14), result semantics (ML.md §3 `CatResult`).
- **With AI:** resume `prefill` / `unknown_terms` / `source` (AI.md §3); AI-12 and AI-14 parts of FE-17 and FE-14.
