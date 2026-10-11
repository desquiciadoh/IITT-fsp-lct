# FE-12 · Talent Search — Plain Pool Search Screen

Route: `/employer/talent`. All UI copy is Russian; this doc is English per the hackathon DoD.

Search across the whole talent pool **without a position context**: no score, no `ScoreBar`,
no reasons/gaps — just identity + league chip + salary tag + shortlist star (the same
`TalentRow` as the FE-10 pool). Filters, facet counters and the candidate drawer are reused
from FE-10; shortlist and «Отправить оффер» (FE-11) work through a position resolved from
`?p=<id>` or the first open position.

## Files

| File | Role |
|---|---|
| `web/src/features/talent/talent-search-page.tsx` | Screen: header, `FilterPanel`, result rows, pagination, `ShortlistTray`, `TalentDrawer`, `SendOfferModal` |
| `web/src/features/talent/search.ts` | Pure logic: prize detection across both `fsp` wire shapes, client-side facet counting (G8), search filtering + pagination, facet capability resolution |
| `web/src/api/scouting.ts` | `useTalentSearch(filters)` hook (`GET /api/talent/search`, shared `filtersToParams` wire format) |
| `web/src/api/types.ts` | `TalentSearchResponse = {items, total, page, pages?, facets?}` (`pages`/`facets` optional — gaps G8/G14) |
| `web/src/mocks/handlers/scouting.ts` | Stateful MSW mock of `GET /api/talent/search` with server-side filters, facets and pagination (`X-Stub: true`) |
| `web/src/mocks/handlers/talent-search.test.ts` | Unit tests for the pure logic + HTTP tests over the mock wire contract |
| `web/src/app/router.tsx` | `/employer/talent` → `<TalentSearchPage/>` (placeholder removed) |

The search handler is registered **before** `*/api/talent/:publicId` (MSW is first-match-wins,
otherwise `search` would be swallowed as a public id).

## Data flow

- **Query:** `GET /api/talent/search?grades=&skills=&fsp=&formats=&salary_max=&confirmed_only=&preset=&page=`
  — exactly the pool's CSV wire format (`filtersToParams`), so the backend selector semantics
  carry over unchanged. Response target shape `{items: TalentShort[], total, page}` plus
  `pages`/`facets` (G8/G14).
- **Rows:** `TalentRow` (identity, league chip, salary tag, star toggle). No scoring column —
  there is no position to match against. Clicking a row opens the drawer via `?c=<public_id>`.
- **Facets:** `resolveFacets()` — server facets win when present; otherwise `computeClientFacets()`
  counts grades/formats/fsp.linked/fsp.prize/confirmed from the returned batch (until the BE
  ships them, per FE2.md "счётчики фасеток считать на клиенте").
- **Prize detection:** the current BE `fsp` serializer ships `{linked, results_count, sports_rank}`
  without `best_tier`; `isPrizeWinner()` uses `best_tier` when present (mock/target shape) and
  falls back to `linked && results > 0 && rank` — so the «призёры ФСП» filter works against both
  payloads. Never hardcoded to mock vs prod: field presence is the capability signal.

## Capability detection (G8/G14)

Same strategy as FE-10: `needsClientFiltering(facets, filters)` triggers the client fallback
(`applyClientSearch`: filter → paginate at `POOL_PAGE_SIZE`, clamp out-of-range pages) whenever
the response lacks `facets` while filters are active. The status line notes when filtering
happened on the client. Against the current backend (which already implements the endpoint but
predates the facets contract in FE2.md) the UI stays correct either way.

## Filters ⇄ URL (single source of truth)

Reuses `useScoutingFilters()` verbatim — a pure hook over search params
(`filtersToParams` / `paramsToFilters`; garbage values ignored, not crashed on). A reload
restores the exact view: filters, page, drawer (`?c=`), offer modal (`?offer=`) and the
shortlist position (`?p=`).

## Shortlist & offers (position-scoped APIs)

Shortlist/offer endpoints are position-scoped, so the page resolves a position from `?p=<id>`
or defaults to the first open one (`usePositions()`); with no positions at all the star/tray/
offer affordances stay hidden rather than broken. Tray cache key is `keys.shortlist(positionId)`
— independent of the search query key, so it survives arbitrary filter changes (same guarantee
as FE-10). Because the search payload carries `shortlisted` on each talent, an effect mirrors
those flags into the tray cache (absorb on add, drop on un-star). «Оффер» opens the FE-11
`SendOfferModal` via `?offer=<public_id>`.

## Mock

`talent/search` handler filters the shared `talentSeed` server-side with AND-across-skills
semantics (matching `apps/matching/selectors.py`), paginates, and returns full `facets` +
`pages` metadata. Responses carry `X-Stub: true`. Reset endpoint: `POST /api/_mock/scouting/reset`.

## Tests (`web/src/mocks/handlers/talent-search.test.ts`, node env)

- `isPrizeWinner` across both `fsp` wire shapes + never prizes an unlinked profile;
- `computeClientFacets` counts grades/formats/fsp/confirmed from the page;
- `matchesSearchFilters` acceptance combo (`fsp=prize` AND `skills=python,django`),
  `preset=fsp_stars` equivalence, pagination and page clamping;
- `resolveFacets` capability detection (server facets win / client fallback / undefined pre-response);
- HTTP over the MSW mock: whole-seed query, acceptance combo, CSV composition
  (`grades=senior&confirmed_only=true`), `salary_max`, and route-shadowing check
  (`/api/talent/search` ≠ `/api/talent/{id}`).

Full suite: 11 files / 111 tests green; `tsc --noEmit` clean; `eslint .` clean.

## Acceptance checklist (FE2.md FE-12)

- Фильтрация «призёры ФСП + стек» работает — ✔ (`fsp=prize&skills=…` server-side in the mock,
  client-side fallback covered by unit tests; asserted end-to-end over HTTP).
- Фильтры/фасетки/пагинация переиспользованы с пула — ✔ (same `PoolFilters` model,
  `FilterPanel`, `TalentRow`, `TalentDrawer`, `POOL_PAGE_SIZE`).
- Счётчики фасеток на клиенте, пока сервер их не отдаёт — ✔ (`computeClientFacets` +
  `resolveFacets` capability detection).
