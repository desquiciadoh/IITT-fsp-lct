# FE-10 · Scouting UI

Screen: `/employer/positions/:id` (router stub replaced by `<ScoutingPage />`).
Scope: view + shortlist only. The offer-send modal belongs to FE-11 and is
deliberately not wired here. All UI text is Russian; code identifiers English.

## Files added / changed

| File | Role |
|---|---|
| `web/src/features/scouting/scouting-page.tsx` | Screen composition: header, shelves, filters, pool, tray, drawer |
| `web/src/features/scouting/filters-bar.tsx` | Filter panel (grades, formats, FSP tri-state, skills, salary_max, confirmed_only, presets) — every control writes to the URL |
| `web/src/features/scouting/shortlist-tray.tsx` | Collapsible sticky tray + `collectShortlist()` cache reader |
| `web/src/features/scouting/candidate-drawer.tsx` | Drawer opened by `?c=<public_id>` with gated contacts |
| `web/src/app/router.tsx` | `/employer/positions/:id` → `<ScoutingPage />` (was FE-14 placeholder) |

Reuses existing domain components unchanged: `TalentRow`, `ScoreBar`,
`ReasonChips`, `LeagueBadge`, `SalaryTag`, `SkillChip`, `EmptyState`,
`ErrorState`, skeletons from `ui/skeleton`.

## Data flow

```
URL (?grades&skills&fsp&formats&salary_max&confirmed_only&preset&page&c)
  └─ useScoutingUrlState → ScoutingFilters          (single source of truth)
       ├─ usePositionPool(id, filters)              GET /api/positions/{id}/pool
       │    └─ no `facets` in response ⇒ client-side fallback (gap G8),
       │       badge "фильтр в браузере" shown in FiltersBar
       ├─ useLeagues(position.specialization)        GET /api/leagues (gap G7 shelves)
       ├─ usePosition(id)                            GET /api/positions/{id} (header)
       ├─ useShortlistToggle(id)                     PUT/DELETE …/shortlist/{pid}, optimistic
       └─ useTalent(?c)                              GET /api/talent/{pid} (drawer, gap G9)
```

- **Page reset**: any filter change resets `page` to 1 inside
  `setFilters` (url-state.ts); pagination itself is client-side slicing of
  the returned pool (`PAGE_SIZE = 5`) because the mock serves one page.
- **Tray resilience (G16)**: `collectShortlist` reads *all* cached pool
  queries for the position during render and dedupes by `public_id`.
  Changing filters never empties the tray; removal from the tray fires the
  same optimistic mutation (`add:false`).
- **Drawer**: opens via row click (`?c=`), closes on backdrop/Esc/X;
  reload restores it. Contacts block shows a lock placeholder while
  `contacts === null` (grant gating); future G9 sections render only when
  the payload carries them.

## States handled

| State | Rendering |
|---|---|
| loading | `Skeleton` header, shelf placeholders, `RowSkeleton` list |
| empty pool | `EmptyState` + «Сбросить фильтры» action |
| error | `ErrorState` with «Повторить» (refetch) for position, pool, drawer |
| refetching with data kept | «обновляем…» hint (`placeholderData` keeps previous list) |

## §5 Integration Tests (stage 5)

Two test files cover the scouting feature end to end:

### `scouting-integration.test.ts` (node env — pure logic, real mock seed data)
- **Client-side fallback (`matchesPoolFilters`)** verified against the actual
  MSW seed of 8 candidates: grades, skills, fsp tri-state (`any`/`linked`/
  `prize`), `salary_max`, `confirmed_only`, and combined filters.
- **Tray resilience**: `collectShortlist` dedupes overlapping cached pool
  queries by `public_id` (simulated page/filter cache overlap).

### `scouting-dom.test.tsx` (happy-dom + MSW node server — full screen render)
- Drawer opens directly from `?c=` on a fresh mount (reload restores state);
  display name resolves asynchronously once pool/detail data settles.
- Contacts gated: mock returns `contacts=null` (gap G9) → lock message, no
  contact values anywhere in the drawer.
- Close via X / backdrop / Esc each removes `?c=` from the URL while other
  filter keys survive; clicking a row writes `?c=` back.
- Simulated reload (unmount → remount at the same URL) restores both drawer
  and filters (`?grades=senior&c=A1B2C3`).
- Shortlist tray keeps a starred candidate after applying filters that hide
  them from the list (stateful PUT/DELETE handlers, gap G16); removing from
  the tray issues DELETE and drops the candidate everywhere.
- Fallback badge «фильтр в браузере» appears because the mock pool response
  ships without `facets` (gap G8); client-side filtering actually narrows
  the visible list (intern shelf → only Сергей Н.).

### Bugs found & fixed by these tests
1. **URL cleanup on drawer close** (`url-state.ts`): `setCandidate(undefined)`
   left a stale empty `c=` segment in the query string — closing the drawer
   unmounted it but the key "stuck" in the URL, so a later reload would not
   restore the intended state. Fixed: explicit removal of the `c` key when
   cleared (verified by X/backdrop/Esc tests asserting exact `location.search`).
2. **Page-reset conflict**: atomic updates that changed both a filter and an
   explicit `page` reset the page unintentionally. Fixed in `setFilters`.
3. **Test-harness fixes** (not product bugs): league shelves come from the G7
   handler in `gaps.ts`, so the DOM test server now mounts `gapHandlers` too;
   async assertions switched to `waitFor`/`findAllByText` to wait for pool,
   talent and leagues queries instead of reading synchronously during
   skeleton state.

## Verification

- `tsc --noEmit`: clean
- `eslint src/api src/features/scouting src/mocks src/app`: clean
  (8 remaining repo-wide errors are pre-existing in FE-05's
  `test-runner-page.tsx` — rules-of-hooks, untouched by FE-10)
- `vitest run`: **83/83 passed** (10 files), incl. 36 scouting tests
  (13 url-state + 7 integration + 10 DOM + 6 mocks/api regressions)
- `vite build`: success

## Out of scope (next tasks)

- Offer-send modal (FE-11) — tray rows currently open the drawer only.
- Server-side filtering/pagination once G8 ships — capability detection is
  already in place (`facets`/`filters_applied` switch off the fallback).
