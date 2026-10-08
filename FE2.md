# FE2.md: Frontend Dev 2 — Test Runner, Employer Side, Lab

> **Audience:** frontend developer 2 and their AI coding agent.
> **Scope:** the qualification **test runner**, every **employer-side** screen (company, position wizard, scouting pool, shortlist, talent drawer, send offer, offers board, talent search), and the Validation Lab and Test Twins (P1).
> **Date:** 2026-10-08. Related files: [FE1.md](FE1.md) (scaffold and shared components; **read it first**), [BE.md](BE.md) (backend and API gaps), [ML.md](ML.md), [AI.md](AI.md).

---

## 0. Before You Start

1. **Wait for FE1's scaffold PR (FE1-0) to merge**, then pull it. Read `web/README.md` and FE1.md §0–§1: product context, UX rules, stack, folder layout, API client, mocks, router and live events. Everything there applies to you.
2. If you start before the scaffold lands, work only inside your feature folders (`src/features/qualification-runner/`, `employer/`, `scouting/`, `talent/`, `offers-employer/`, `lab/`) on a branch, and rebase afterwards.
3. **Use FE1's shared components** (`components/domain/`): `SalaryTag`, `StatusChip`, `ReasonChips`, `ScoreBar` (with `normalizeComponents()`), `OfferCard`, `TalentRow`, `LeagueBadge`, `RatingBadge`, `FspBadge`, `TrustBadge`, `EmptyState`, `ErrorState`, `useCountdown`. If you need a new shared component, add it to `components/domain/` with a `/dev/ui` entry and tell FE1.
4. **The backend is Django + DRF.** The generated OpenAPI client is the contract. Missing pieces are BE gaps G1–G17 ([BE.md §2.3](BE.md)). **Mock every gap with MSW in its target shape** (`src/mocks/handlers/<feature>.ts`, response header `X-Stub: true`), so nothing changes when BE ships it.
5. **UI language: Russian. Code: English.** UX rules: one primary action per screen; **salary and status always visible**; verified and declared evidence look different; WCAG AA; loading, empty and error states everywhere.

---

## 1. Your Tasks

IDs refer to `docs/TASKS.md` §2.6. The "Backend now" lines describe the actual Django API today, as of merge `3cf4044`.

### P0

- [ ] **FE-05 · Test runner** (L). Routes `/candidate/qualification/start` and `/candidate/qualification/:id`.
  - **Start screen.**
    - Read `specialization` and `claimed_grade` from the query string (FE1's onboarding links here).
    - Call `GET /api/assessments/eligibility?specialization=` → `{can_start, next_attempt_at?, promotion_available, reason?, active_session_id?}`. If `active_session_id` is set, offer to **resume** that session. If `reason === 'cooldown_active'`, show a countdown.
    - Let the candidate choose the mode (`full | express`) and read the rules.
    - `POST /api/assessments {specialization, claimed_grade, mode}` → 201 session.
    - Errors: 429 `cooldown_active`, 409 `assessment_in_progress`.
  - **Item view.**
    - `GET /api/assessments/{id}` → `{id, specialization, claimed_grade, kind, mode, status, current, ...}`.
    - `current` = `{item_id, seq, stem_md, code: {lang, text} | null, options: [{id, text_md}] | null, input_type: 'choice'|'number'|'text', time_limit_s, deadline_at, served_at}`.
    - Render the stem with react-markdown and the code with **Shiki** (lazy; `python`, `javascript`, `sql`). Show options as a radio list, or a number or text input for typed formats.
  - **Answer.**
    - `POST /api/assessments/{id}/answers {item_id, option_id? , value?, integrity: {focus_loss, paste}}` → `{done: false, next}` or `{done: true, result}`.
    - When done, navigate to FE1's `/candidate/qualification/:id/result`.
    - Errors: 409 `item_not_current` (refetch the session and continue); `assessment_expired` (show the expired state).
  - **Timer.** Count down from `deadline_at` with `useCountdown`. Correct for clock skew by measuring against `served_at` and the local receive time. At zero, auto-submit the current selection, or an empty answer. The server will count late answers as incorrect once BE fixes B12.
  - **Integrity capture.** Count `visibilitychange` (hidden) events and `paste` events per item, and send them with the answer. Show them neutrally; never accuse.
  - **Navigation.** No back navigation (`replace` history; block back with a confirm). A refresh resumes via `GET /assessments/{id}`.
  - **Progress.** `seq / max_items` and a difficulty indicator from `level`. **Both fields are missing today** (gap G5): show "Вопрос N" without a total and hide the indicator until they arrive.
  - **Leaving early.** "Завершить досрочно" calls `POST /assessments/{id}/finish` (G5; mocked) with a confirm dialog.
  - **Backend now:** a session has **only 3 items**, with no adaptivity yet (ML is building the CAT engine, ML.md). **The client never receives correctness per item; don't try to show it.**
  - *Done:* a full run completes against the backend and against an 8-item mock; a refresh mid-test resumes; the timer auto-submits; it works at phone width (the QR "wow" demo option).
- [ ] **FE-09 · Company & position wizard** (M).
  - **Company** (`/employer/company`): `GET`/`PUT /api/companies/me` with `{name, inn, website, email_domain, business_domain, description, contact_email}`; `trust_level` is read-only and shown as `TrustBadge`.
    - **Note:** the backend currently auto-creates a company for employers without one, which is a security bug (BE.md B1). After the fix, the API returns 403 `company_required`, and you must show a "create company" form (gap G17).
  - **New position** (`/employer/positions/new`):
    1. Paste a JD into a textarea, then call `POST /api/positions/parse {text}` → `{draft, unknown_terms, blueprint: [{topic, weight}], source}` (gap G6; mock it).
    2. Show an editable form: title, specialization, grades (multi-select), **must and nice skills as editable chips** (names from `GET /api/taxonomy`, gap G3; highlight `unknown_terms`), work formats, location, **salary_min / salary_max / salary_type** (required; gross/net is an explicit radio with **no default**), team_context, description, allow_adjacent, is_public.
    3. Show blueprint bars.
    4. Save with `POST /api/positions`.
  - **Validation.** Use zod: `salary_min > 0`, `salary_max ≥ salary_min`, `salary_type` required. **Validate client-side before submit.** The backend currently returns **500** for `salary_min = 0` (BE.md B15), and it labels every validation error `salary_invalid`, with `errors` as a dict.
  - **Edit** (`/employer/positions/:id`): settings tab with `GET`/`PUT /api/positions/{id}`.
  - **Employer dashboard** (`/employer`): positions list (`GET /api/positions` returns an array) and an offers summary.
  - *Done:* a sample JD becomes a saved position (mocked parse, real save); invalid salaries never reach the server.
- [ ] **FE-10 · Scouting** (L), route `/employer/positions/:id`.
  - **League shelves:** `GET /api/leagues?specialization=` → `[{specialization, grade, confirmed, unconfirmed, median_expectation?}]` (gap G7; mock it).
  - **Ranked pool:** `GET /api/positions/{id}/pool` → `{items, total, page}`. Each item is `{talent, score, components, reasons, shortlisted}`.
    - `talent` = `{public_id, city, work_formats, salary_min, salary_max, salary_type, league {specialization, grade, status, rating, percentile, strength}, fsp {linked, results_count, sports_rank}, skills [{id, name, source}], last_active_at}`.
    - `components` is today a **dict** `{skill, grade, strength, fsp, salary}` (max 35/25/15/15/10). It will become a list `{key, value, weight, contribution}[]` (gap G8). Always go through `normalizeComponents()`.
    - `reasons` = `[{kind, text, source?}]`.
    - Render each row with `TalentRow`, `ScoreBar` and `ReasonChips`. Show `gaps` (target G8); until then, derive them from `kind === 'minus'` reasons.
  - **Filters,** synced to the URL: grades, skills, FSP (`any | linked | prize`), formats, salary_max, confirmed_only, preset, page.
    - Send them as query params.
    - **The backend ignores them today** (no filters, facets or pagination; G8). When the response has no `facets`, apply the filters client-side as a fallback; that's fine for the mini seed. Detect the capability; don't hardcode it.
  - **Shortlist tray:** `PUT` / `DELETE /api/positions/{id}/shortlist/{public_id}` → 204. Update optimistically. The tray must **survive filter changes**. There is no "list shortlist" endpoint yet (gap G16), so build the tray from `shortlisted: true` pool items for now.
  - **Candidate drawer:** `?c=<public_id>` → `GET /api/talent/{public_id}` → talent fields plus `about`, `experience_text`, and `contacts` (`null` unless the company has a grant; then `{full_name, email, phone, telegram}`). Sections for topics, assessments and integrity flags come later (gap G9): hide them when absent. Add a "Отправить оффер" button.
  - A reload restores the whole view (filters, drawer) from the URL.
  - *Done:* after changing filters 10 times the shortlist is intact; reload restores the view; contacts appear only after acceptance.
- [ ] **FE-11 · Send Offer & offers board** (M).
  - **Send Offer modal** (from a pool row or the drawer): `POST /api/offers {candidate_public_id, position_id, title, description, salary_min, salary_max, salary_type, contact_channel: 'email'|'phone'|'telegram'|'platform', contact_value, expires_in_days?}`.
    - Prefill the salary from the position.
    - **Always send `salary_type` explicitly**: the backend silently defaults to gross today (B15).
    - **Never send `why_you`**: the server computes it (BE fix B9).
    - Show errors by code: 422 `salary_invalid`, 403 `candidate_not_reachable`, 404.
  - **Offers board** (`/employer/offers`): `GET /api/offers?status=` returns an **array**, grouped into status columns (sent, viewed, accepted, declined, withdrawn, expired, interview, hired, closed).
    - **Withdraw** is allowed in `sent` and `viewed` (`POST /api/offers/{id}/withdraw {version}`). On 409 `version_conflict` or `invalid_transition`, refetch.
    - Live updates come through events, or 10 s polling while SSE is broken (B14).
  - **Contacts panel:** after acceptance, `offer.candidate_contacts = {full_name, email, phone, telegram}`. Today it is filled **only while `status === 'accepted'`**; BE will base it on the grant instead (B16).
  - **Backend gap:** the employer offer payload has **no candidate identity** (gap G10, `talent: TalentShort`). Mock it, and meanwhile show the title, salary, status and dates.
  - *Done:* send → the candidate window updates (live or ≤ 10 s) → accept → contacts appear on the board.
- [ ] **FE-12 · Talent search** (S), route `/employer/talent`.
  - `GET /api/talent/search` → `{items: TalentShort[], total, page}`. There are no filters, facets or pagination yet (G8, G14).
  - Reuse the scouting filters, `TalentRow` and the drawer. Compute facet counts client-side until the server returns them.
  - *Done:* filtering by FSP prize-winners plus a stack works.

### P1

- [ ] **FE-13 · Validation Lab** (M), route `/lab` (public).
  - `GET /api/lab/report` → `ValidationReport` (shape in `docs/TASKS.md` §1.4; gap G11). Until it exists, use ML's `validation/out/report.fixture.json`.
  - **Show a red "FIXTURE" banner whenever `synthetic_fixture` is true.** Fake numbers must never reach the jury unlabeled.
  - Charts (Recharts):
    - confusion matrix heatmap;
    - accuracy, QWK and retest KPIs;
    - TIF line chart;
    - leak-attack bars (static vs parametric);
    - systems table with nDCG@10 and P@10 bars;
    - non-FSP parity and pool p95.
- [ ] **FE-14 · Test Twins & Blueprint Builder** (S). JD → blueprint → two unique test instances side by side, with the same difficulty profile. Depends on BE-22 (`/lab/twins?position_id=`) and ML-12; mock it until then.
- [ ] **FE-17 · Pool power features** (M).
  - Weight presets (balanced / skills / budget) and sliders that re-rank live.
  - Counterfactual hints from `relaxations` ("убрать Kubernetes → +23 кандидата").
  - An acceptance-likelihood badge next to "Send".
  - A Need Health panel (decline analytics).
  - A below-salary-floor warning before sending.
  - Depends on ML-10 and BE-20; mock it until then.
- [ ] **FE-18 · Polish (your half)** (M, shared with FE1). The test runner and the offers board and modal are responsive on phones. Plus a contrast check and loading, empty and error states across the employer screens.

---

## 2. Coordination

- **With FE1:** FE1 owns the scaffold, `api/client.ts`, `api/events.ts`, the router, the guards and `components/domain/`. You own the feature folders listed in §0. Review each other's PRs. **The handoff routes:** FE1's onboarding → your `/candidate/qualification/start`; your runner → FE1's `/candidate/qualification/:id/result`.
- **With BE:** regenerate the client when `docs/openapi.json` changes (`pnpm api:schema && pnpm api:gen`). Your blockers: G3 (taxonomy), G5 (runner fields, finish), G6 (JD parse), G7 (leagues), G8 (pool filters, facets, components list), G9 (talent card sections), G10 (employer offer talent), G11 (lab report), G12 (SSE), G13 (error shape), G14 (pagination), G16 (shortlist list), G17 (company create). Add new needs to BE.md §2.3 as gap rows.
- **With ML:** semantics of `components`, `reasons`, `gaps`, `relaxations`, `ItemView.level` and `max_items`, and the `ValidationReport` (ML.md §3, §5).
- **With AI:** `JdParseResult` semantics: editable chips, `unknown_terms` and the `source` badge (AI.md §3).
- PR titles start with the task ID (`FE-10 Scouting pool`). Keep PRs small.
