# FE1.md: Frontend Dev 1 — Scaffold, Design System, Shell, Candidate Side

> **Audience:** frontend developer 1 and their AI coding agent.
> **You start today.** Your first deliverable is the **web scaffold**. Frontend dev 2 ([FE2.md](FE2.md)) builds on it, so merge it as early as possible, ideally by the end of today.
> **Scope:** project scaffold, API client and mocks, design tokens and the shared domain components, auth and app shell, live updates, Jury Mode, and every **candidate-side** screen except the test runner (FE2 owns the runner).
> **Date:** 2026-10-08. Related files: [FE2.md](FE2.md), [BE.md](BE.md) (backend and API gaps), [ML.md](ML.md), [AI.md](AI.md).
>
> **Status (2026-10-09, branch `fe1-p0-tasks`):** all Rework items **R1–R15 are fixed** (one commit each) and a clean clone is green (`pnpm install --frozen-lockfile && typecheck && lint && test && build`). Remaining: **R16** (open the PR) and **R17** (tell FE2 after merge). Until then P1 stays on hold.

---

## 0. Product Context (read once)

FSP Draft is a reverse-recruitment platform for the Russian Federation of Sports Programming (LCT 2026 hackathon).
1. **Candidates** take an adaptive test once and land in a **League** (specialization × grade). Their grade is either **confirmed** or **unconfirmed**.
2. **Employers** browse ranked, explained pools and send **Draft Offers**. Every offer must state a salary range in RUB per month, marked gross or net.
3. **Candidate contacts stay hidden until the candidate accepts an offer.**
4. FSP sports achievements boost ranking but never the grade.

**UI language: Russian.** Code, comments and identifiers are in English.

**UX rules (from ARCHITECTURE §4.4):**
- One primary action per screen.
- **Salary and status are always visible.**
- **Verified and declared data always look different.** Evidence sources are `test` (verified by test), `fsp` (verified by FSP), `microtask` and `declared`.
- WCAG AA contrast.
- Every screen needs loading, empty and error states.

**Coding rules:** follow `.agents/rules/react-coding-style.md`, `react-patterns.md` and `typescript-coding-style.md` (referenced by `AGENTS.md`).

**Backend reality (important):** the backend is **Django + DRF**, not FastAPI. Its contract is the generated OpenAPI schema. `docs/TASKS.md` §1.4 describes the *target* API. Where the two differ, **the generated schema wins**, and missing pieces are tracked as gaps G1–G17 in [BE.md §2.3](BE.md). Mock every gap with MSW in its *target* shape so the code doesn't change when BE ships it.

---

## 1. FE1-0 · Scaffold (TODAY; blocks FE2)

**Location: `web/` at the repo root.** Not `apps/web`: `apps/` is the Django package root.

### Stack
- pnpm, Vite, **React 19**, TypeScript `strict`, ESLint (typescript-eslint) and Prettier.
- Tailwind CSS with **shadcn/ui**: use the current stable CLI, and add components as you need them.
- **React Router** (data router, `createBrowserRouter`).
- **TanStack Query v5**.
- **react-hook-form** with **zod** for forms.
- **sonner** for toasts (via shadcn).
- **Recharts** for charts.
- **react-markdown** for item stems and markdown copy. **Shiki** (lazy-loaded) for code; FE2 uses it in the runner.
- **orval** for the typed client and React Query hooks.
- **MSW v2** for mocks.
- **Vitest** for unit tests. Playwright arrives in P1 (FE-19).

### Folder layout (this is the convention FE2 follows)
```text
web/
  openapi/schema.json            # copied/converted backend schema (input for orval)
  orval.config.ts
  src/
    app/          router.tsx, providers.tsx, layouts/, guards/ (RequireAuth, RequireRole, OnboardingGate)
    api/
      generated/  # orval output: NEVER edit by hand
      client.ts   # fetch mutator: cookies, CSRF, problem+json → ApiError
      keys.ts     # every TanStack Query key in one place
      events.ts   # SSE → query invalidation, with polling fallback
    components/
      ui/         # shadcn primitives
      domain/     # LeagueBadge, RatingBadge, SalaryTag, StatusChip, ReasonChips, ScoreBar, OfferCard, TalentRow, ...
    features/     # one folder per feature: pages/, components/, hooks/
      auth/ jury/ onboarding/ candidate/ qualification-result/ settings/        ← FE1
      qualification-runner/ employer/ scouting/ talent/ offers-employer/ lab/   ← FE2
    mocks/        browser.ts, handlers/<feature>.ts, fixtures/<feature>.ts
    i18n/         ru.ts (UI strings), errors.ts (error code → Russian message)
    lib/          format.ts (money, dates), labels.ts (RU labels for enums), hooks (useCountdown, ...)
    styles/       tokens.css
  README.md       # conventions for FE2 and the AI agents: how to add a route, query, mock, component
```

### API layer
- **Schema source.** `pnpm api:schema` fetches `http://localhost:8000/api/schema/?format=json` into `openapi/schema.json` when the backend runs. Otherwise it converts the committed `../docs/openapi.json`, which is currently **YAML despite the `.json` name** (`npx js-yaml ../docs/openapi.json > openapi/schema.json`). Commit `openapi/schema.json`.
- **Generation.** `pnpm api:gen` runs orval with `client: 'react-query'`, `httpClient: 'fetch'` and `mutator: src/api/client.ts`.
- **`client.ts`** must do four things:
  - Use same-origin requests (`/api/...`) with `credentials: 'include'`.
  - For unsafe methods, send **`X-CSRFToken`** read from the `csrftoken` cookie. That is Django's header; ignore the `X-Requested-With` note in TASKS §1.4. If no cookie exists yet, call `GET /api/auth/csrf` once (gap G1; ignore a 404 until BE ships it). Django sets `csrftoken` after login.
  - Turn any non-2xx response into a thrown `ApiError { status, code, title, detail, fieldErrors: Record<string, string[]> }`. **Normalize both error shapes the backend currently emits** (BE.md B18): `errors: [{field, msg}]` and `errors: {field: [msg, ...]}`. Treat `detail` that starts with `{'` as junk (a Python repr) and show the Russian message for `code` instead.
  - Handle `204` responses with no body.
- **Vite dev proxy.** Proxy `/api` to `http://localhost:8000`. Keep `changeOrigin: false` (the default). Django's CSRF origin check then matches `http://localhost:5173`.
- **Mocks.** `VITE_API_MOCKS=all|missing|off`.
  - `all` mocks every endpoint, so no backend is needed.
  - `missing` mocks only the BE gaps (G1–G17) and passes the rest through.
  - Mocked responses set the header **`X-Stub: true`**; the e2e test asserts none remain on the golden path.
  - Fixtures follow the generated types, or the TASKS §1.4 shapes for endpoints that don't exist yet.
- **Live events.** `useLiveEvents()` is mounted in authenticated layouts. It opens `new EventSource('/api/events', { withCredentials: true })` and applies this invalidation map: `offer.*` → `['offers']` and `['offer', id]`; `league.updated` → `['pool']` and `['leagues']`; `fsp.synced` → `['profile']`. **The backend SSE currently returns 406** (BE.md B14), so on `error` the hook closes the stream and switches to **polling**: a shared flag sets `refetchInterval: 10_000` on the offers queries and on the employer pool and offers queries. Retry SSE every 60 s.

### Router (create placeholder pages for **all** routes, including FE2's)
```text
/                                  → redirect by role and onboarding step
/jury                              FE1   Jury Mode
/login · /register · /verify       FE1
/candidate/onboarding/:step        FE1   consent → profile → survey → claim
/candidate/qualification/start     FE2   start screen (eligibility, mode, rules)
/candidate/qualification/:id       FE2   test runner
/candidate/qualification/:id/result FE1  result
/candidate                         FE1   dashboard: league status, offers inbox, history
/candidate/offers/:id              FE1   offer detail
/candidate/settings                FE1   privacy, consents, FSP link
/employer                          FE2   dashboard: positions, offers summary
/employer/company                  FE2
/employer/positions/new            FE2   paste JD → chips → save
/employer/positions/:id            FE2   shelves + pool + shortlist (drawer: ?c=<public_id>)
/employer/talent                   FE2   talent search
/employer/offers                   FE2   offers board
/lab                               FE2   Validation Lab (public)
/dev/ui                            FE1   component gallery
```

### Guards
- `RequireRole` uses `GET /api/me` → `{ id, role, email, email_verified, demo, company_id, onboarding_step }`.
- `onboarding_step` is currently one of `consent | profile | qualification | done`.
- Candidates with `onboarding_step !== 'done'` go to the matching onboarding step. `qualification` sends them to `/candidate/qualification/start`.

### Done
- `pnpm dev` with `VITE_API_MOCKS=all` gives a navigable placeholder for every route.
- With the backend running, `POST /api/demo/persona` logs in through the proxy and `/api/me` resolves the role.
- `pnpm typecheck && pnpm lint && pnpm build && pnpm test` are green.
- `web/README.md` documents the conventions.
- **Merge, then tell FE2.**

**Running the backend locally:** it needs PostgreSQL, then `python manage.py migrate && python manage.py seed --mode=mini && python manage.py runserver`. `runserver` **currently fails** because `config/wsgi.py` is missing (BE.md B13). Until BE fixes that or ships docker compose, work with `VITE_API_MOCKS=all`.

---

## 1A. Rework after review of `c0d8731` (DO THIS FIRST)

> **For the AI agent:** work on branch `fe1-p0-tasks`. Fix items in order; one commit per item, message prefixed with the item ID (e.g. `R1 Track web/src/lib`). Do **not** start P1 tasks until every R-item below is checked. All paths are relative to `web/` unless stated otherwise.

### Review verdict

| Task | Implementation | "Done" criterion |
|---|---|---|
| FE1-0 Scaffold | ✅ stack, layout, `client.ts`, `events.ts`, `keys.ts`, all routes, README | ❌ clean clone fails `typecheck`/`build` (R1); mock modes wrong (R4); not merged early |
| FE-01 Components | ✅ all components, `normalizeComponents` tested | ⚠️ `useCountdown` not committed (R1) |
| FE-02 Shell & auth | ✅ login/register/verify, errors by `code`, field errors | ❌ expired session does not return to `/login` (R6) |
| FE-03 Jury Mode | ✅ guide, personas, time travel, reset | ❌ page requires auth, judges can't open it (R3) |
| FE-04 Onboarding | ✅ 4 steps, resume prefill, `unknown_terms` | ⚠️ refresh on survey loses prefill (R8) |
| FE-06 Result | ✅ all variants, cooldown, PDF content-type check | ❌ unreachable for a new candidate (R2) |
| FE-07 Offers | ✅ view/accept/decline state machine, 409 recovery, polling | ⚠️ raw enum codes in UI (R9) |
| FE-08 Settings | ✅ | — |

Verified on a clean checkout: `pnpm lint` ✅, `pnpm test` ✅ (17/17), **`pnpm typecheck` ❌ 43 × TS2307 `Cannot find module '@/lib/...'`**, so `pnpm build` ❌.

### Blockers (merge is impossible until these are fixed)

- [x] **R1 · `web/src/lib/` is not in git.** The root `.gitignore` has the Python rule `lib/` (line 14), which silently ignores `web/src/lib/`. 41 imports point to it: `@/lib/utils`, `@/lib/labels`, `@/lib/format`, `@/lib/personas`, `@/lib/hooks/useCountdown`. Your local build is green only because the files exist on your disk.
  - **Fix:** in the root `.gitignore`, directly after the `lib/` / `lib64/` lines, add `!web/src/lib/`. Then `git add web/src/lib` and commit.
  - **Also:** `package.json` pins `"packageManager": "pnpm@12.10.1"`; on the reviewer's machine pnpm could not bootstrap that version. Pin the version the team actually runs (`pnpm -v`) or remove the field.
  - **Acceptance:** in a fresh directory, `git clone … && cd web && pnpm install --frozen-lockfile && pnpm typecheck && pnpm lint && pnpm test && pnpm build` is green. Paste the output into the PR description.

- [x] **R2 · `OnboardingGate` blocks the test runner and the result page.** The backend keeps `onboarding_step === 'qualification'` until the candidate has a confirmed/unconfirmed league, i.e. **until the test is finished** (`apps/identity/views.py:150`). `src/app/guards.tsx:37` redirects every path except `/candidate/qualification/start`, so `/candidate/qualification/:id` (FE2 runner) and `/candidate/qualification/:id/result` bounce back to `/start`. The golden path cannot complete.
  - **Fix:** when `step === 'qualification'`, allow any `location.pathname.startsWith('/candidate/qualification/')`; redirect everything else to `/candidate/qualification/start`.
  - **Acceptance:** add `src/app/guards.test.ts` (extract the decision into a pure function `onboardingRedirect(me, pathname): string | null` and test it): `qualification` + `/candidate/qualification/abc` → `null`; `qualification` + `/candidate/qualification/abc/result` → `null`; `qualification` + `/candidate` → `/candidate/qualification/start`; `consent` + anything → `/candidate/onboarding/consent`; `done` → `null`.

- [x] **R3 · `/jury` and `/lab` are behind auth.** `src/app/router.tsx:83` puts `/jury` inside `RequireAuth`; `/lab` (line 132) is inside `RequireRole role="employer"`. Jury Mode is the **entry page for anonymous judges**; `/lab` is **public** (FE2.md).
  - **Fix:** move both routes to the top-level public list (next to `/login`). Wrap them in `AppLayout` only if the layout renders correctly without a user (no nav crash when `useMe` returns 401); otherwise give them a minimal public layout. Do **not** mount `useLiveEvents()` for anonymous users.
  - **Also:** anonymous `/` currently redirects to `/login`; redirect it to `/jury` instead (keep `/login` reachable from the Jury page).
  - **Acceptance:** in a private window with no cookies, `/jury` renders; clicking "Анна" lands on `/candidate`; `/lab` renders a placeholder without login.

- [x] **R4 · Mock modes do not match the contract (§1 API layer).**
  - **`missing` must mock only real gaps.** `src/mocks/browser.ts:213` adds `demoHandlers` in `missing` mode. `POST /api/demo/persona` and `POST /api/demo/time-travel` **exist on the backend**; mocking them means no session cookie is set and `/api/me` (not mocked in this mode) returns 401, so persona login is broken. Only `POST /api/demo/reset` (G4) is a gap. Split `demo.ts` so `missing` gets only `reset`.
  - **Do not mix fixtures into real data.** `src/mocks/handlers/gaps.ts` `GET /api/assessments` prepends three fake attempts to the real history in `missing` mode. Remove that handler from `missing` (the endpoint exists). Keep the `demo-*` result fixtures for `/dev/ui` and `all` mode only. The real result endpoint lacks G5 fields; the UI already hides those sections, which is the intended behaviour.
  - **`all` must cover every endpoint FE1 screens call.** Add stateful handlers (in `handlers/offers.ts`, `handlers/assessments.ts`, `handlers/fsp.ts`, fixtures in `fixtures/`) for: `GET /api/offers`, `GET /api/offers/:id`, `POST /api/offers/:id/{view,accept,decline}` (bump `version`, enforce the state machine, return 409 `invalid_transition` / `version_conflict` problem+json), `GET /api/assessments/eligibility`, `GET /api/assessments`, `POST /api/fsp/link` (409 `fsp_id_already_linked` for a fixed id, e.g. `taken-123`), `POST /api/fsp/sync`, `GET /api/candidates/me/card.pdf` (return a tiny PDF with `content-type: application/pdf`).
  - Mocked `/api/me` must advance `onboarding_step` when consents / survey are saved, so the wizard → gate flow is realistic in `all` mode.
  - **Acceptance:** with `VITE_API_MOCKS=all` and no backend, a candidate persona can walk consent → profile → survey → claim → (runner placeholder) and open dashboard, an offer (view → accept, and view → decline), result fixtures and settings with zero failed requests in the console. With `VITE_API_MOCKS=missing` and the live backend, persona login works and no response on the persona/onboarding/offers path carries `X-Stub`.

### Architecture deviations (fix in this PR)

- [x] **R5 · One source of truth for API types.** `src/api/generated/` (orval, ~3.6k lines) is committed but imported nowhere; features use hand-written DTOs in `src/api/types.ts`. Hand-written hooks around `customFetch` are **accepted** as a deviation from "orval hooks", but types must not drift from the backend.
  - **Fix:** for every DTO that exists in the schema (`Offer`, `CandidateProfile`, `AssessmentResult`/`AssessmentSession`, `MeResponse`, `ConsentsResponse`, `FSPLinkResponse`, enums), re-export or derive from `@/api/generated/models` in `src/api/types.ts`. Keep hand-written types **only** for gap/target shapes (G3 taxonomy, G5 result extras, G8 score list, G14 `{items}`), each with a `// gap Gx` comment. Remove the duplicate `Reason`/`Source` types from `components/domain/reason-chips.tsx` and import them from `@/api/types`.
  - Configure orval to emit models only if the generated hooks are not going to be used (`client: 'fetch'` or drop the hooks file) so there is no dead code; document the choice.
  - **Fix `web/README.md`** ("Для FE2" §2 says "use the orval client"): describe what FE2 must actually do — hooks in `src/api/<feature>.ts` via `customFetch`, types from `@/api/types`, keys from `@/api/keys`.
  - **Acceptance:** `grep -r "api/generated" src --include=*.ts* | grep -v src/api/generated` returns at least the `types.ts` imports; `pnpm typecheck` green.

- [x] **R6 · Expired session must return to `/login` (FE-02 Done).** There is no global 401 handling and `useMe` is not refetched (`refetchOnWindowFocus: false`), so a dead session shows error states on every screen.
  - **Fix:** in `src/app/providers.tsx` create the client with `queryCache: new QueryCache({ onError })` and `mutationCache: new MutationCache({ onError })`; on `ApiError` with `status === 401` and the request not being `/api/auth/login`, call `queryClient.clear()` and `router.navigate('/login', { replace: true })` (keep `?next=` for the current path).
  - In `src/api/client.ts:98`, the 401 fallback code must be `unauthorized` (add the Russian text "Сессия истекла, войдите снова" to `i18n/errors.ts`), not `bad_credentials`. Only the login form maps 401 to `bad_credentials` (the backend already sends that code explicitly).
  - **Logout and persona switch:** replace `invalidateQueries({ queryKey: ['me'] })` with `queryClient.clear()` before navigating (`app/layouts/app-layout.tsx:25`, `features/auth/login-page.tsx:29`, `features/jury/jury-page.tsx`), and seed `keys.me` with the persona/login response via `setQueryData`, so the next screen never shows the previous user's cached offers/profile or redirects by the old role.
  - **Acceptance:** delete the `sessionid` cookie in devtools while on `/candidate/offers` → within one request you are on `/login` with the "Сессия истекла" toast; switching Anna → employer lands directly on `/employer` without a `/candidate` flash.

- [x] **R7 · Verified vs declared must look different (UX rule).** In `components/domain/reason-chips.tsx` the only difference is a small muted icon with a `title` tooltip.
  - **Fix:** declared reasons get a **dashed border** and muted text; verified (`test`, `fsp`) get a solid border plus a visible short label (`тест`, `ФСП`) next to the icon, not only a tooltip. Apply the same convention to skill chips on the profile/prefill form. Show every variant on `/dev/ui`.

- [x] **R7b · Palette deviation.** `styles/tokens.css` implements "Arena (dark)" instead of the FE1-01 palette (`#0369a1` primary, etc.). Do not change it yet; the lead decides. Until then keep all colour values inside `tokens.css` only (no raw hex in components) and verify WCAG AA for `--fsp-muted` on `--fsp-panel` and for status colours used as text.

### Smaller fixes (same PR)

- [x] **R8 · Survey step loses prefill on refresh.** `features/onboarding/steps/survey-step.tsx` computes `defaultValues` from `useProfile()` before the profile loads and never resets. Render a skeleton while `isLoading`, then call `reset(valuesFromProfile)` once data arrives (or mount the form only after load). Same check for `profile-step.tsx` and `claim-step.tsx`.
- [x] **R9 · No raw enum codes in the UI.** `features/offers/offer-detail-page.tsx:126` shows `decline_reason` raw ("salary") and line 180 shows `«{offer.status}»` raw. Use `DECLINE_REASON_LABEL` / the status labels from `lib/labels.ts`. Grep the candidate features for other `{x.status}`, `{x.grade}`, `{x.specialization}` rendered directly.
- [x] **R10 · Auto-view can get stuck.** In `offer-detail-page.tsx:51`, if `POST /view` fails (409), `autoViewed` stays set and the page shows "Открываем оффер…" forever. On a conflict, reset the ref after refetch so the view is retried once with the new `version`; on any other error show the `ErrorState` with a retry button.
- [x] **R11 · Decline modal accessibility.** Replace the hand-made overlay in `features/offers/decline-modal.tsx` with the shadcn `Dialog` (`pnpm dlx shadcn@latest add dialog`): Esc closes, focus is trapped and returns to the trigger. Reset `reason`/`comment` when the modal reopens.
- [x] **R12 · Eligibility default.** `api/assessments.ts:88` falls back to `'backend'` when the specialization is unknown, so a frontend/ML candidate can see the wrong cooldown. Disable the query (`enabled: Boolean(specialization)`) instead of defaulting.
- [x] **R13 · Charts.** Topic and evidence charts are plain `div`s although `recharts` is a dependency. Either switch to Recharts (preferred, consistent with FE2) or remove `recharts` from `package.json`. Keep `shiki`: FE2 uses it in the runner (FE2.md FE-12).
- [x] **R14 · Nested page shells.** `OnboardingPage` and `JuryPage` render their own `<main className="min-h-screen …">` inside `AppLayout`'s `<main>`. Use a `<section>`/`<div>` without `min-h-screen` when rendered inside the layout.
- [x] **R15 · Docs.** On your branch, `docs/TASKS.md` F-06 says "`apps/web/`, `npm run build`". Correct it to "`web/`, `pnpm build`". In `web/README.md` replace the "Структура" block with the real tree (it says `features/ auth/ (login)` only).

### Process

- [ ] **R16 ·** Open a PR `fe1-p0-tasks → main` titled `FE1-0 FE-01..08 Scaffold and candidate screens`. Description: the review table above with every R-item ticked, the clean-clone command output from R1, and screenshots of `/jury` (anonymous), onboarding, result (3 variants), offer detail and settings.
- [ ] **R17 ·** After merge, tell FE2 immediately (they are blocked on `components/domain/`, `lib/labels`, `useCountdown` and the router). From now on: **one PR per task ID**, small, reviewed by FE2.

---

## 2. Your Feature Tasks

IDs refer to `docs/TASKS.md` §2.6. The "Backend now" lines describe the actual Django API today, as of merge `3cf4044`.

### P0

- [x] **FE-01 · Design tokens & shared domain components** (M). **FE2 depends on these. Build them right after the scaffold.**
  - **`tokens.css`:** a placeholder palette until the FSP brand book arrives (PD-02 has no owner yet). Primary `#0369a1`, accent `#0284c7`, FSP gold `#f59e0b`, success `#16a34a`, warning `#ea580c`, slate neutrals. Plus typography and the shadcn theme.
  - **Components,** each typed with props and shown in **every state** on `/dev/ui` from fixtures:
    - `LeagueBadge {specialization, grade, status}`: confirmed and unconfirmed must look clearly different.
    - `RatingBadge {rating, ci?}`: shows "1085 ± 60".
    - `SalaryTag {min, max, type}`: "250 000 – 320 000 ₽ · gross/на руки". Always show the type.
    - `StatusChip {status: OfferStatus}`.
    - `ReasonChips {reasons: {kind: 'plus'|'minus'|'info', text, source?}[]}`: one icon per source, so verified and declared look different.
    - `ScoreBar {components}`: stacked contributions. **Accept both shapes:** today's dict `{skill, grade, strength, fsp, salary}` (points out of 35/25/15/15/10) and the target list `{key, value, weight, contribution}[]` (BE gap G8). Put a `normalizeComponents()` helper with unit tests in `lib/`.
    - `OfferCard {offer, viewer: 'candidate'|'employer'}`: salary first, then company and trust badge, status and expiry.
    - `TalentRow {talent, score?, reasons?, shortlisted?, onToggleShortlist?}`.
    - `FspBadge` (rank and best tier) and `TrustBadge` (company `none|domain|verified`).
    - `EmptyState`, `ErrorState` (takes an `ApiError`), skeletons.
    - `useCountdown(deadline)`: FE2 uses it in the runner, and you use it for cooldowns.
  - *Done:* every component state renders on `/dev/ui`; `normalizeComponents` is tested.
- [x] **FE-02 · Shell, auth & live updates** (M).
  - **Screens:** login, register (role: candidate or employer only) and verify.
  - **Plumbing:** `useMe`, guards, layouts with a role-aware nav and logout, toasts, and errors rendered **by `code`** through `i18n/errors.ts`. Codes: `validation_failed`, `bad_credentials`, `email_taken`, `rate_limited`, `forbidden`, `not_found`, `salary_invalid`, `cooldown_active`, `assessment_in_progress`, `item_not_current`, `assessment_expired`, `not_finished`, `candidate_not_reachable`, `invalid_transition`, `version_conflict`, `contact_not_granted`, `fsp_id_already_linked`, `api_error`. Field errors land on the form fields.
  - **Backend now:**
    - `POST /api/auth/register {email, password (min 6), role}` → 201 `{user_id, email, role, email_verified}`.
    - `POST /api/auth/login {email, password}` → `{id, role, email, email_verified, demo, company_id}`; a wrong password gives 401 `bad_credentials`.
    - `POST /api/auth/logout` → 204.
    - `POST /api/auth/verify-email` is **missing** (G2). In DEMO_MODE, accounts are auto-verified, so the verify page shows a "confirmed" state; mock the token flow.
  - *Done:* register, verify (mocked), login and redirect by role all work. An expired session goes back to `/login`.
- [x] **FE-03 · Jury Mode landing** (S).
  - A short Russian guide for judges (draft the copy yourself; the PD stream has no owner).
  - Persona buttons call `POST /api/demo/persona {persona: 'candidate_fsp'|'candidate_plain'|'employer'}`. Those are Anna (FSP champion, Senior), Alex (no FSP, Middle) and the Yandex Tech employer; the seed must have run.
  - A **time travel** control: `POST /api/demo/time-travel {days}` → `{clock_offset_days}`.
  - **Reset** (`POST /api/demo/reset`, gap G4, mocked).
  - A link to `/lab`.
  - *Done:* one click logs in a persona and lands on the right dashboard.
- [x] **FE-04 · Onboarding wizard** (M). Steps: consent → profile → survey → claim.
  - **Consent:** three separate checkboxes, each with its own text: processing, publication to employers (152-FZ art. 10.1) and FSP data sync. Draft the Russian texts and mark them "needs legal review". Submit with `PUT /api/candidates/me/consents {processing, publication, fsp_sync, version: '1.0'}` → `{processing, publication, fsp_sync}`.
  - **Profile:**
    - A resume drop zone. `POST /api/candidates/me/resume` as multipart with field `file` (PDF, 5 MB or less) → `{prefill, unknown_terms, source: 'llm'|'rules'}`.
    - The **backend parsing is currently fake** and returns the same skills every time (AI.md AI-F1), so build against the target shape.
    - A prefill review form. **Highlight `unknown_terms`** and show a source badge.
    - Error `unreadable_pdf` falls back to the manual form.
  - **Survey:** specialization (`backend|frontend|ml_data`), years, roles, work formats (`office|hybrid|remote`), salary expectation (`salary_min`, `salary_max`, `salary_type` gross/net) and private salary floor (`salary_floor`). Save with `PUT /api/candidates/me` (partial, **flat fields**; `skills` is a list of strings; `contacts` is `{email, phone, telegram}`).
  - **Claim:** grade cards with Russian descriptors from `GET /api/taxonomy` (gap G3; mock it: intern, junior, middle, senior). Then navigate to `/candidate/qualification/start?specialization=…&claimed_grade=…`; FE2's start screen creates the session.
  - **Backend now:** `GET /api/candidates/me` returns the full profile (creates it on first call) including `skills`, `league`, `fsp` and `consents`. **Validation errors on `PUT /candidates/me` come back as `errors: {field: [msg]}`** (dict shape).
  - *Done:* the wizard completes against mocks and the real backend; 422 errors land on the right fields; a refresh resumes the right step.
- [x] **FE-06 · Result & history** (M), route `/candidate/qualification/:id/result`.
  - **League card:** rating ± CI, percentile and decision copy.
    - **Confirmed:** "Грейд подтверждён".
    - **Unconfirmed:** "заявлен, не подтверждён" with a note that the profile stays visible but ranked lower.
  - **Charts:** topic bars and an evidence chart (item level vs correct).
  - **CTAs:** fallback (`instant` or `short_test`), promotion, a cooldown countdown, and **Player Card download** (`GET /api/candidates/me/card.pdf`). If the response `content-type` is not `application/pdf`, the server fell back to HTML: show an error.
  - **History:** `GET /api/assessments`. It returns an **array** today; also accept `{items}` (gap G14).
  - **Backend now:** `GET /api/assessments/{id}/result` → `{id, specialization, claimed_grade, kind, mode, status, theta, se, rating, result_grade, decision, promotion_unlocked, counts_as_attempt, started_at, finished_at}`. **Missing** (gap G5; mock them, and hide sections when absent): `rating_ci`, `percentile`, `topics`, `evidence`, `fallback`, `next_attempt_at`. Cooldown comes from `GET /api/assessments/eligibility?specialization=` → `{can_start, next_attempt_at?, reason?, active_session_id?}`.
  - *Done:* the confirmed, unconfirmed + fallback and promotion variants all render from fixtures.
- [x] **FE-07 · Candidate dashboard & offers** (M).
  - **Dashboard:** a status card (league badge, cooldown) and an **offers inbox** of `OfferCard`s with salary first.
  - **Offer detail** (`/candidate/offers/:id`): opening an offer with `status === 'sent'` sends `POST /api/offers/{id}/view {version}`. **Accept** works only from `viewed` (`POST /accept {version}`). **Decline** opens a modal with a required reason (`salary|stack|format|company|timing|not_looking|other`) and an optional comment (`POST /decline {version, reason, comment}`).
  - **Conflicts:** on 409 `version_conflict` or `invalid_transition`, refetch and toast.
  - Live status comes through events or polling.
  - **Backend now:**
    - `GET /api/offers?status=` returns an **array**.
    - An offer is `{id, company {id, name, trust_level, ...}, position, title, description, salary_min, salary_max, salary_type, currency, contact_channel, contact_value, status, decline_reason, decline_comment, why_you: Reason[], version, expires_at, created_at, updated_at}`.
  - *Done:* an offer sent from the employer side appears (live or within 10 s); declining requires a reason; a version conflict recovers.
- [x] **FE-08 · Candidate settings** (S), route `/candidate/settings`.
  - **Privacy:** `blind_mode`, `open_to_offers`, `salary_floor`, and a company blocklist (`blocked_company_ids`). There is no company lookup endpoint yet (gap G17), so show the list read-only and mock the picker.
  - **Consents:** withdrawing shows a warning: "профиль будет скрыт от работодателей".
  - **FSP link:** today it's `POST /api/fsp/link {participant_id}` → `{participant_id, sports_rank, sync_status, results_count}` (409 `fsp_id_already_linked`). The target is an OIDC redirect, `GET /api/auth/fsp-id/login?intent=link` (gap G15). Build the button so switching is a one-line change.
  - **Sync:** a button calling `POST /api/fsp/sync`. Show the results list from `profile.fsp.results`.
  - *Done:* toggles persist; the FSP link round-trips; the 409 shows a clear message.

### P1

- [ ] **FE-15 · Vacancies & applications** (M). Candidate: list, apply, statuses. Employer: publish toggle and applicant pipeline (coordinate with FE2 on the employer pages). Depends on BE-17; mock it until then.
- [ ] **FE-16 · Micro-tasks** (M). Candidate inbox and solve; employer create, review and invite from a submission. Depends on BE-18.
- [ ] **FE-18 · Polish** (M, shared with FE2). A Russian copy pass across the app, a contrast check, and loading, empty and error states everywhere. Candidate screens must be responsive on phones (FE2 does the runner and the employer screens).
- [ ] **FE-19 · Playwright e2e** (S). The golden path against the docker compose stack, two browser contexts:
  1. Persona login.
  2. Onboarding.
  3. The test.
  4. Result.
  5. Employer pool.
  6. Send offer.
  7. Candidate accepts.
  8. Contacts appear.

  **Assert that no response carries `X-Stub`.** Runs in CI once BE adds the workflow.

---

## 3. Coordination

- **With FE2:** you own `components/domain/`, `api/client.ts`, `api/events.ts`, the router and the guards. FE2 may add domain components; anything used by both features goes into `components/domain/` with a `/dev/ui` entry. Review each other's PRs.
- **With BE:** regenerate the client whenever `docs/openapi.json` changes (`pnpm api:schema && pnpm api:gen`). When you need a backend change, add it to BE.md §2.3 as a gap row instead of hacking around it. Current blockers for you: G1 (CSRF endpoint), G2 (verify-email), G3 (taxonomy), G4 (demo reset), G5 (result fields), G12 (SSE), G13 (error shape), G14 (pagination), G15 (FSP OIDC), G17 (company lookup).
- **With AI:** `prefill`, `unknown_terms` and `source` semantics for the resume step (AI.md §3).
- **With ML:** result semantics (rating ± CI, topics, evidence, fallback, promotion; ML.md §3 `CatResult`).
- PR titles start with the task ID (`FE-04 Onboarding wizard`). Keep PRs small.
