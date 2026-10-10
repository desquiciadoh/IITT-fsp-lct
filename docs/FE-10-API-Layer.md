# FE-10 · Scouting — API Layer & Mocks

Scope: types, hooks, MSW handlers and URL-state plumbing for the employer
Scouting screen (`/employer/positions/:id`). No UI components in this layer.
Source of truth for requirements: `docs/FE2.md` §"FE-10 · Scouting".

## 1. Types (`web/src/api/types.ts`)

Hand-written view types that wrap or extend the Orval-generated schema, one per
OpenAPI gap:

| Type | Gap | Purpose |
| --- | --- | --- |
| `LeagueShelf`, `LeagueShelvesResponse` | G7 | `GET /api/leagues` is not in the spec yet. Shelf shape: `{ specialization, leagues: League[] }`. The mock previously returned a candidate-side payload; it now returns the employer shelf used by the league rows on the scouting header. |
| `PoolComponentsInput` | G8 | Union accepted by `normalizeScoreComponents`: flat dict (`{ base: 40, skills: 30 }`) as served today **or** normalized array `ScoreComponent[]` once BE ships `components: [{ key, label, value }]`. |
| `PoolItemView` | G8 | Pool row as served: `TalentShort` fields + raw `components: PoolComponentsInput` + optional `gaps` (missing reasons surfaced inline). |
| `ScoutingPoolResponse` | G8 | Envelope of `GET /api/positions/{id}/pool`: `items`, `total`, optional `facets` (server-side facet counts) and optional `gaps`. When `facets` is absent the client falls back to local filtering (see §2). |
| `TalentDetail` | G9 | Wrapper over generated talent schema: adds `about`, `experience_text` and gated `contacts` (`null` until the company holds a contact grant). Drawer hides sections that are absent. |
| `ScoutingFilters` | — | Full URL-state shape: `grades`, `skills`, `fsp` (tri-state `any \| linked \| prize`), `formats`, `salary_max`, `confirmed_only`, `preset`, `page`, `candidate` (drawer deep-link `?c=<public_id>`). |

## 2. Hooks (`web/src/api/scouting.ts`)

All queries go through the shared `customFetch` (generated client) and keys
from `src/api/keys.ts`, so cache invalidation stays consistent with FE-05 code.

- **`useLeagues(specialization?)`** — `GET /api/leagues?specialization=`. Feeds
  the league shelves; stable key allows sharing between screens.
- **`usePositions()` / `usePosition(id)`** — list + detail for the screen header
  (title, specialization, salary band).
- **`usePositionPool(positionId, filters)`** — `GET /api/positions/{id}/pool`
  with query params serialized by `filterParams()` (only non-default filters
  are sent, keeping URLs and cache keys minimal).
  - **Server-vs-client duality:** if the response contains `facets`, the pool is
    trusted as already filtered server-side. If `facets` is missing (current
    mock and current BE), items are re-filtered locally with
    `matchesPoolFilters(item, f)` — grade/skills/fsp/formats/salary/confirmed.
    Pagination is applied after filtering in fallback mode.
- **`useShortlistToggle(positionId)`** — optimistic `PUT/DELETE
  /api/positions/{id}/shortlist/{public_id}`:
  - `onMutate` patches every cached pool page *and* the shortlist id-set, so
    the tray survives filter changes and refetches;
  - `onError` rolls back from the snapshot captured in `onMutate`;
  - `onSettled` invalidates pool + shortlist to reconcile with the server.
- **`useTalent(publicId)`** — drawer data (`GET /api/talent/{public_id}`);
  enabled only when `publicId` is defined (i.e. `?c=` present).

Helpers exported for tests/reuse: `filterParams`, `matchesPoolFilters`,
`expandGradePreset` (preset ± adjacent grades per FE2.md).

## 3. Mocks (`web/src/mocks/handlers/scouting.ts`)

Registered in `src/mocks/browser.ts` under both `all` and `missing` modes
(the latter keeps G7/G8/G9 endpoints mocked because they don't exist in the
spec at all).

- **Seed:** 8 deterministic candidates spanning grades, formats, skill tags,
  FSP statuses and salary bands; two of them intentionally fail several client
  filters to exercise the fallback path.
- **`GET /api/positions/:id/pool`** — responds **without `facets`** on purpose
  (forces the client-side fallback in dev/tests) and serializes `components`
  as a flat dict (G8 reality). Accepts the same query params as the real API.
- **`PUT/DELETE /api/positions/:id/shortlist/:publicId`** — backed by a
  module-level stateful `Set`, so the tray persists across requests and can be
  asserted in tests (optimistic UX + resilience to filter changes).
- **`GET /api/talent/:publicId`** — returns full detail with
  `contacts: null` (G9 gating: no grant → no contacts visible in the drawer).
- **`GET /api/leagues` (`handlers/gaps.ts`)** — fixed to return the
  `LeagueShelvesResponse` shape (G7): previously it served a candidate-side
  payload incompatible with the employer shelves.

## 4. URL-state (`web/src/features/scouting/url-state.ts`)

The URL is the single source of truth (FE2.md requirement):

- `serializeFilters(filters) -> URLSearchParams` — omits defaults, CSV for
  multi-values, `confirmed_only=1`, drawer as `c=<public_id>`.
- `parseFilters(params) -> ScoutingFilters` — validated round-trip: unknown
  grades/formats/fsp values are dropped, malformed numbers ignored, defaults
  restored. Never throws (URLs are user-editable).
- `useScoutingUrlState(positionId)` — wraps react-router `useSearchParams`:
  - reload restores filters/page/drawer from the URL;
  - any filter change resets `page` to 1 (only `page` changes keep other
    params);
  - derived query keys flow into TanStack Query automatically — no duplicate
    state layer.
- Unit tests: `url-state.test.ts` (13 cases covering serialization, parsing,
  defaults, page-reset and drawer semantics).

## 5. Verification

- `pnpm typecheck` — clean.
- `pnpm lint` — clean (two pre-existing `no-explicit-any` errors in FE-05's
  `qualification.test.ts` were annotated with scoped disables).
- `pnpm test` — 60/60 passing. The previously failing qualification test №3
  ("late auto-submit graded incorrect") was fixed: the clock override closed
  over the captured `servedAt` made time static, so `now > deadline` could
  never hold; the test now freezes a mutable clock before session start and
  advances it past the 60 s window + 3 s grace.
