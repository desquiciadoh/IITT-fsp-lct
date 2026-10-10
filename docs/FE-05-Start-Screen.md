# FE-05 · Test Runner — Stage 2: Start Screen

Component: `web/src/features/qualification-runner/start-page.tsx` (`StartPage`)
Route: `/candidate/qualification/start` (react-router, lazy-loaded; runner lives at `/candidate/qualification/:sessionId`)
All UI copy is Russian; this doc is English per hackathon DoD ("document briefly in English in docs").

## 1. Eligibility-driven state machine

On mount the page calls `GET /api/assessments/eligibility?specialization=<spec>` via the
`useEligibility(spec)` hook. The response selects one of five views through the pure,
unit-tested helper `resolveStartView(eligibility, isLoading, isError)`:

| View        | Condition                                             | UI |
|-------------|-------------------------------------------------------|----|
| `loading`   | query in flight                                       | `CardSkeleton` |
| `error`     | query error, missing payload, or unknown block reason | `ErrorState` with retry (`refetch`) — fails closed |
| `resume`    | `active_session_id != null` (checked **before** cooldown) | "У вас незавершённый тест" + **«Продолжить тест»** → navigates to `/candidate/qualification/{active_session_id}` |
| `cooldown`  | `can_start: false` and `reason === 'cooldown_active'` | live countdown card (see §2) |
| `form`      | `can_start: true`                                     | Full/Express start form (see §3) |

Resume takes priority over cooldown because an interrupted session must always be
reachable; the backend mirrors this ordering in the mock.

## 2. Cooldown countdown

- `countdownTo(next_attempt_at, nowMs)` → `{done, hours, minutes, seconds}`; `formatCountdown` renders `HH:MM:SS` (monospace, `role="timer"`).
- A `setInterval` tick re-renders once per second **only while view === 'cooldown'** (interval cleaned up on unmount/view change).
- When the timer hits zero, the page automatically `refetch`es eligibility, so the start form unlocks itself without a manual reload.
- The 48 h window comes from the backend contract (MK3 cooldown after a graded attempt); the mock computes `next_attempt_at = now + 48h` when a finished session exists.

## 3. Start form (Full / Express) & validation

- `react-hook-form` + `zodResolver(startFormSchema)`. Fields:
  - `specialization`: enum `backend | frontend | ml_data` (select) — changing it re-keys the eligibility query (`keys.eligibility(spec)`), so resume/cooldown state is per specialization.
  - `claimed_grade`: enum `intern | junior | middle | senior` — defines the decision cut server-side (FE2.md §FE-05).
  - `mode`: radio `full` («Полный», ~12 items) / `express` («Экспресс», ~6 items).
- Validation is entirely schema-level (enums, defaults `junior`/`full`); submit is disabled while `createAssessment` mutation is pending (double-click guard).
- On submit: `useCreateAssessment().mutate(values)`:
  - `onSuccess(session)` → `navigate('/candidate/qualification/' + session.id)`. The mutation already primes `keys.session(id)` in the Query cache, so the runner renders item 1 without an extra GET.
  - `onError`: normalized `ApiError` (from `client.ts`). Code `assessment_in_progress` (race with another tab / stale eligibility) triggers an eligibility refetch so the UI flips to the resume view; any other error shows a Russian `sonner` toast.

## 4. API hooks used

From `web/src/api/assessments.ts` (Stage 1):

| Hook / fn            | Endpoint                          | Role on this screen |
|----------------------|-----------------------------------|---------------------|
| `useEligibility(spec)` | `GET /api/assessments/eligibility` | drives the whole state machine |
| `useCreateAssessment()` | `POST /api/assessments`           | starts a session; body `{specialization, claimed_grade, mode}`; returns first session incl. served `current` item |
| `useSession(id)`       | `GET /api/assessments/{id}`        | not called here — used by the runner for resume (cache primed by create) |

Query keys are centralized in `src/api/keys.ts`; CSRF + cookie auth handled transparently by `customFetch`.

## 5. Testing with MSW mocks

The stateful qualification mock (`web/src/mocks/handlers/qualification.ts`) implements the full session store (8-item bank, cursor persistence, scoring) and is active only in **`all` mode**:

```bash
cd web
VITE_API_MOCKS=all pnpm dev   # no backend needed
```

Manual scenarios on `/candidate/qualification/start`:

1. **Fresh user → form:** clear localStorage/session (or call `resetQualificationMock()`), open the page → `can_start: true` → Full/Express form. Submit → redirect to runner with item 1 served.
2. **Resume:** start a test, answer 2 items, close the tab, reopen `/start` → eligibility returns `active_session_id` → «Продолжить тест» → runner resumes at item 3 (cursor kept in the mock's module-level store, survives page reloads like a real backend).
3. **Cooldown:** finish (or abandon) a session → back to `/start` → countdown card ticking down from 48:00:00. To demo expiry quickly, temporarily lower the mock's `+ 48 * 60 * 60 * 1000` offset (line computing `next_attempt_at`) to e.g. `+ 10_000` — when the timer reaches zero the form reappears automatically.
4. **Error path:** run with `VITE_API_MOCKS=missing` (qualification endpoints fall through to the 503 gap-handler) → `ErrorState` with retry.

Unit tests (`start-page.test.ts`, node env, no DOM): 7 cases covering `countdownTo` (incl. past/expired → `done`), `formatCountdown` padding, and every branch of `resolveStartView` (priority of resume over cooldown, fail-closed on unknown reason). Run with `pnpm test` in `web/`.

## 6. Known gaps

- `mode` is stored by the mock but item-count adaptation (6 vs 12) lands with the runner (Stage 3) / backend G5.
- Real backend currently serves 3 items and lacks `max_items`/`level`; the mock adds them so the runner can be built ahead of BE work.
