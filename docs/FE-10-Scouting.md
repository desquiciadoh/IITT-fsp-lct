# FE-10 · Scouting — Position Pool Screen

Route: `/employer/positions/:id` (tabs «Пуул» / «Настройки», active tab in `?tab=`).
All UI copy is Russian; this doc is English per the hackathon DoD.

## Files

| File | Role |
|---|---|
| `web/src/features/employer/position-detail-page.tsx` | Tab shell: pool tab + FE-09 settings form (`GET/PUT /api/positions/{id}`) |
| `web/src/features/employer/pool-tab.tsx` | Scouting pool orchestration (shelves, filters, rows, pagination, relaxations, tray, drawer) |
| `web/src/features/scouting/filters.ts` | URL-synced filter state, client-side fallback (G8), gaps/relaxations derivation, shelf aggregation |
| `web/src/features/scouting/league-shelves.tsx` | League shelves component (G7) |
| `web/src/features/scouting/filter-panel.tsx` | Filter panel with facet counters when the server provides them |
| `web/src/features/scouting/shortlist-tray.tsx` | Shortlist tray sidebar (G16) |
| `web/src/features/scouting/talent-drawer.tsx` | Candidate drawer `?c=<public_id>` (G9) |
| `web/src/api/scouting.ts` | React Query hooks: leagues, pool, shortlist toggle, talent, tray |
| `web/src/mocks/handlers/scouting.ts` | Stateful MSW mock of all gap endpoints in target shape (`X-Stub: true`) |
| `web/src/features/scouting/filters.test.ts` | Pure-logic unit tests + HTTP tests over the mock |

Handlers are registered in `mocks/browser.ts` **before** `employerHandlers` and in `mocks/server.ts`.

## Data flow

- **League shelves (G7):** `GET /api/leagues?specialization=` → `[{specialization, grade, confirmed, unconfirmed, median_expectation?}]`, rendered by `LeagueShelves`; counts aggregated via `summarizeShelves()`.
- **Ranked pool:** `GET /api/positions/{id}/pool?page=&…filters`. Each item `{talent, score, components, reasons, shortlisted}`. `components` goes through `normalizeComponents()` so both today's dict shape (`{skill, grade, strength, fsp, salary}`, max 35/25/15/15/10) and the target list shape (`{key, value, weight, contribution}[]`, G8) render identically in `ScoreBar`.
- **Reasons/gaps:** `ReasonChips` renders `reasons [{kind, text, source?}]`; `deriveGaps()` shows explicit `gaps` when present (target G8) and otherwise derives them from `kind === 'minus'` reasons.
- Rows use `TalentRow` (identity, league chip, salary tag, star toggle) + `ScoreBar` + gaps line. Clicking a row opens the drawer via `?c=`.

## Filters ⇄ URL (single source of truth)

`useScoutingFilters()` serializes `{grades, skills, fsp, formats, salary_max, confirmed_only, preset, page}` into query params (`filtersToParams` / `paramsToFilters` in `api/scouting.ts`; garbage values are ignored, not crashed on). A reload therefore restores the exact view.

**Capability detection (G8):** the real backend ignores filter params and returns no `facets`. `needsClientFiltering(facets, filters)` triggers a client-side fallback (`applyClientFilters`: same AND semantics, sort by score desc, paginate at `POOL_PAGE_SIZE`, clamp out-of-range pages) whenever the response lacks `facets` while filters are active. Nothing is hardcoded to "mock vs prod" — presence of `facets` is the capability signal. The status line notes when filtering happened on the client. Relaxation hints come from `pool.relaxations` when shipped, else `deriveRelaxations()` proposes loosening the dimensions that currently exclude most candidates.

## Shortlist tray (G16)

`PUT/DELETE /api/positions/{id}/shortlist/{public_id}` → 204, applied optimistically (`useToggleShortlist`). There is no list endpoint yet, so the tray accumulates `shortlisted: true` pool entries across batches (`useShortlistTray.absorb/reconcile`) and additionally tries `GET …/shortlist` (target shape) with graceful fallback. Because the tray lives in its own cache key (`keys.shortlist(positionId)`) and only merges batch deltas, it **survives arbitrary filter changes**. `ShortlistTray` renders the sidebar: click selects (opens drawer), star removes.

## Candidate drawer (G9)

`?c=<public_id>` → `GET /api/talent/{public_id}` → talent fields plus `about`, `experience_text`, and `contacts` — `null` unless the company holds a grant (accepted offer), then `{full_name, email, phone, telegram}`. Sections for topics/assessments/integrity flags are hidden when absent (they arrive later with G9). Actions: **«Отправить оффер»** (navigates to the FE-11 offer flow with `?c=`) and shortlist toggle. Closes on Esc/overlay; closing just removes `?c=` while keeping tab + filters.

## Mock

`scoutingHandlers` is stateful (module-level store, reset via `POST /api/_mock/scouting/reset` used by tests): server-side filtering **with facets** and pagination (so the client fallback path is exercised only against the real BE), shortlist CRUD, tray list, contacts gating (`t-002` has a grant). All stub responses carry `X-Stub: true`.

## Tests (`web/src/features/scouting/filters.test.ts`, node env)

- filters ⇄ params roundtrip incl. garbage tolerance;
- `matchesFilters` AND semantics across every dimension;
- `applyClientFilters` filtering/sorting/pagination/clamping;
- `deriveGaps` / `deriveRelaxations` / `summarizeShelves`;
- HTTP tests over the MSW mock: pool filters+facets, shortlist PUT/DELETE → 204, tray list, contacts gating.

Full suite: 9 files / 76 tests green; `tsc --noEmit` reports no errors in FE-10 files (remaining errors are pre-existing FE-09 files); eslint clean for all FE-10 code.

## Acceptance checklist

- After changing filters 10 times the shortlist is intact — tray cache is independent of the pool query key. ✔
- Reload restores the whole view (tab, filters, drawer) from the URL alone. ✔
- Contacts appear only after acceptance — drawer renders contacts only when the API ships them (grant-gated in the mock). ✔
