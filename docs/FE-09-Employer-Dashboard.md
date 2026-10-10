# FE-09 · Employer Dashboard (`/employer`)

Stage 3 of the **Company & position wizard** feature (FE-09). This page is the employer's landing
area: it summarizes open positions and outreach activity, and gates on company existence
(backend bug **B1** / gap **G17**).

## Dashboard structure

The page (`web/src/features/employer/dashboard-page.tsx`) is composed of three blocks:

1. **Header**
   - Company name + `TrustBadge` (read-only trust level assigned by moderation).
   - Primary action button **«Создать новую вакансию»** → navigates to `/employer/positions/new`
     (the wizard from Stage 2).

2. **Positions list** (`GET /api/positions`, hook `usePositions()`)
   - One card per position: title, specialization and grades labels (from `src/lib/labels.ts`),
     salary range with gross/net suffix, work formats, location, status chip (`open`/`paused`/`closed`).
   - Cards link to `/employer/positions/:id` (edit screen — separate stage).
   - Skill chips show `must_skills` first; `nice_skills` are visually de-emphasized.

3. **Offers summary**
   - Counters grouped by offer status: `sent`, `viewed`, `accepted` (+ declined).
   - Data source: `GET /api/offers` via the existing offers API layer. The backend has no
     aggregation endpoint yet, so counts are computed **client-side** (see below). When a real
     `/api/offers/summary` endpoint lands, replace the client aggregation with that query.

## Client-side offer aggregation — `countOffersByStatus()`

Defined in `web/src/features/employer/dashboard-helpers.ts`:

```ts
export function countOffersByStatus(offers: Offer[]): Record<OfferStatus, number>
```

- Single `O(n)` pass over the offers array, incrementing a counter per `offer.status`.
- Every known status key is pre-initialized to `0`, so the UI never renders `undefined` for
  empty buckets (e.g. no offers yet → all counters show `0`).
- Unknown/unexpected status values are ignored defensively (forward-compatible with backend
  enum additions).
- Fully covered by unit tests (`dashboard-helpers.test.ts`): empty list, mixed statuses,
  unknown status tolerance.

## B1 / G17 handling — missing company

The backend no longer auto-creates a company record. `GET /api/companies/me` returns
`403 company_required` until the employer fills in the company profile.

On the dashboard this is detected via `isCompanyRequired(err)` (same helper used by the wizard):

- Instead of a raw error state, the page renders an **informational banner**:
  «Чтобы публиковать вакансии, сначала создайте профиль компании» with a CTA button linking to
  `/employer/company`.
- The positions list still renders below the banner (positions cannot exist without a company,
  so in practice the list will be empty; the mock store also gates `POST /api/positions` on
  company existence with the same 403).

This keeps the flow discoverable: employer sees *why* they cannot create a vacancy and one click
away from fixing it.

## Loading / error / empty states

| State | Rendering |
| --- | --- |
| Positions loading | `RowSkeleton` placeholder cards (3 rows) |
| Positions error | `ErrorState` with Russian message + «Повторить» retry button |
| Positions empty | Empty-state card with hint + «Создать первую вакансию» CTA |
| Offers loading | Skeleton counters block |
| Offers error | Silent degrade: summary shows zeros — offers data is secondary on this page |
| No company (403) | Banner described above (not treated as a hard error) |

All visible strings are in Russian per project conventions; code identifiers and file paths are English.

## Mocks

Served by the stateful employer MSW handlers (`web/src/mocks/handlers/employer.ts`, Stage 0):

- `GET /api/positions` returns the seeded demo position («Python-разработчик (демо-вакансия)»)
  plus any positions created during the session.
- All stub responses carry the `X-Stub: true` header.
- `resetEmployerMock()` clears company/positions between tests.

## Verification

- `npx vitest run src/features/employer/ src/mocks/handlers/employer.test.ts` → 33/33 green.
- `tsc --noEmit` and ESLint on all touched files → clean.
