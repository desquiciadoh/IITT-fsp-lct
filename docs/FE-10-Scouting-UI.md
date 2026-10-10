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

## Verification

- `tsc --noEmit`: clean
- `eslint src/features/scouting src/app/router.tsx`: clean
- `vitest run`: 60/60 passed (incl. 13 url-state tests)
- `vite build`: success

## Out of scope (next tasks)

- Offer-send modal (FE-11) — tray rows currently open the drawer only.
- Server-side filtering/pagination once G8 ships — capability detection is
  already in place (`facets`/`filters_applied` switch off the fallback).
