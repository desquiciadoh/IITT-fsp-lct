import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { filtersToParams, paramsToFilters } from '@/api/scouting'
import type { Grade, LeagueShelf, PoolEntry, PoolFilters, TalentShort, WorkFormat } from '@/api/types'

/**
 * FE-10 · Scouting filters.
 *
 * The URL query string is the single source of truth: every filter change is
 * a `setSearchParams` replace, so reload / back-forward restores the whole
 * view (filters + drawer). `?c=<public_id>` belongs to the drawer and is
 * preserved across filter updates.
 */

export const EMPTY_FILTERS: PoolFilters = {
  grades: [],
  skills: [],
  fsp: 'any',
  formats: [],
  salary_max: null,
  confirmed_only: false,
  preset: null,
  page: 1,
}

export function filtersFromSearchParams(sp: URLSearchParams): PoolFilters {
  return paramsToFilters(sp)
}

export function useScoutingFilters(): [PoolFilters, (next: Partial<PoolFilters>) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  // Memoize on the serialized filter part so unrelated param writes (?c=…)
  // do not re-render the pool with a fresh object identity.
  const filterKey = useMemo(
    () => filtersToParams(filtersFromSearchParams(searchParams)).toString(),
    [searchParams],
  )
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [filterKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const setFilters = (next: Partial<PoolFilters>) => {
    const merged: PoolFilters = { ...filters, ...next }
    // Any explicit filter change resets pagination unless the caller kept page.
    if (!('page' in next)) merged.page = 1
    const params = new URLSearchParams(searchParams)
    for (const key of [
      'grades',
      'skills',
      'fsp',
      'formats',
      'salary_max',
      'confirmed_only',
      'preset',
      'page',
    ]) {
      params.delete(key)
    }
    for (const [key, value] of filtersToParams(merged)) params.set(key, value)
    setSearchParams(params, { replace: true })
  }

  return [filters, setFilters]
}

export function activeFilterCount(f: PoolFilters): number {
  let n = 0
  if (f.grades.length) n++
  if (f.skills.length) n++
  if (f.fsp !== 'any') n++
  if (f.formats.length) n++
  if (f.salary_max != null) n++
  if (f.confirmed_only) n++
  if (f.preset) n++
  return n
}

// --- capability detection & client-side fallback (gap G8) --------------------

/**
 * The backend ignores filters today. If the response carries `facets`, server
 * filtering is live — don't touch the items. Otherwise apply the same filter
 * semantics client-side; fine for the mini seed. Detect, never hardcode.
 */
export function needsClientFiltering(
  facets: Record<string, Record<string, number>> | undefined,
  filters: PoolFilters,
): boolean {
  if (facets) return false
  return activeFilterCount(filters) > 0
}

export function matchesFilters(talent: TalentShort, f: PoolFilters): boolean {
  const league = talent.league as
    | { grade?: string; status?: string; strength?: number | null }
    | null
    | undefined
  if (f.grades.length && !f.grades.includes((league?.grade ?? '') as Grade)) return false
  if (f.confirmed_only && league?.status !== 'confirmed') return false
  if (f.formats.length && !talent.work_formats?.some((x) => f.formats.includes(x as WorkFormat))) {
    return false
  }
  if (f.salary_max != null && (talent.salary_min ?? Infinity) > f.salary_max) return false
  if (f.skills.length) {
    // talent.skills is string[] in the pool payload; tolerate {name} objects too.
    const names = (talent.skills ?? []).map((s) => String(typeof s === 'string' ? s : s.name).toLowerCase())
    if (!f.skills.some((skill) => names.includes(skill.toLowerCase()))) return false
  }
  const fsp = talent.fsp as { linked?: boolean; best_tier?: string } | undefined
  if (f.fsp === 'linked' && !fsp?.linked) return false
  if (f.fsp === 'prize' && !(fsp?.linked && ['winner', 'prize_winner'].includes(fsp.best_tier ?? ''))) {
    return false
  }
  if (f.preset === 'fsp_stars' && !(fsp?.linked && ['winner', 'prize_winner'].includes(fsp.best_tier ?? ''))) {
    return false
  }
  if (f.preset === 'confirmed' && league?.status !== 'confirmed') return false
  return true
}

/**
 * Fallback pipeline: filter → sort by score desc → paginate (20/page), so the
 * UI behaves identically to the target server contract (G8).
 */
export const POOL_PAGE_SIZE = 20

export function applyClientFilters(
  data: { items: PoolEntry[]; total: number; page: number } | undefined,
  filters: PoolFilters,
): { items: PoolEntry[]; total: number; page: number; pages: number } {
  const items = (data?.items ?? []).filter((i) => matchesFilters(i.talent, filters))
  items.sort((a, b) => b.score - a.score)
  const total = items.length
  const pages = Math.max(1, Math.ceil(total / POOL_PAGE_SIZE))
  const page = Math.min(Math.max(1, filters.page), pages)
  return {
    items: items.slice((page - 1) * POOL_PAGE_SIZE, page * POOL_PAGE_SIZE),
    total,
    page,
    pages,
  }
}

/** Keep the tray cache in sync with every pool batch we render (gap G16). */
export function useAbsorbShortlist(
  items: PoolEntry[] | undefined,
  absorb: (items: PoolEntry[]) => void,
  reconcile: (items: PoolEntry[]) => void = () => {},
) {
  const signature = (items ?? []).map((i) => `${i.talent.public_id}:${i.shortlisted}`).join('|')
  useEffect(() => {
    if (items) {
      absorb(items)
      reconcile(items)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])
}

// --- derived gaps (FE2.md §FE-10: target `gaps` is gap G8) -------------------

/**
 * Until the backend ships explicit `gaps`, derive them from the reasons:
 * every `kind === 'minus'` reason is a gap. Entries already carrying `gaps`
 * (target shape) pass through untouched — capability detection, not hardcoding.
 */
export function deriveGaps(entry: PoolEntry): string[] {
  if (entry.gaps) return entry.gaps
  return entry.reasons.filter((r) => r.kind === 'minus').map((r) => r.text)
}

// --- league shelves helpers (gap G7) ------------------------------------------

export type ShelfTotals = { confirmed: number; unconfirmed: number; median: number | null }

/** Aggregate shelves into totals; median = median of non-null medians. */
export function summarizeShelves(shelves: LeagueShelf[]): ShelfTotals {
  const confirmed = shelves.reduce((n, s) => n + s.confirmed, 0)
  const unconfirmed = shelves.reduce((n, s) => n + s.unconfirmed, 0)
  const meds = shelves
    .map((s) => s.median_expectation)
    .filter((m): m is number => typeof m === 'number' && m > 0)
    .sort((a, b) => a - b)
  const median = meds.length ? meds[Math.floor((meds.length - 1) / 2)] : null
  return { confirmed, unconfirmed, median }
}
