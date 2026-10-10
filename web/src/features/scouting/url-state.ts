/**
 * FE-10 · Scouting URL-state.
 *
 * The URL is the single source of truth for filters, pagination and the
 * candidate drawer (`?c=<public_id>`). A reload must restore the whole view
 * (FE2.md §FE-10 "Done" criteria). Changing any filter resets `page` to 1;
 * changing only `page` keeps everything else.
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { FspFilter, Grade, ScoutingFilters, WorkFormat } from '@/api/types'

// --- validation tables ---------------------------------------------------------

const GRADES: readonly Grade[] = ['intern', 'junior', 'middle', 'senior']
const FORMATS: readonly WorkFormat[] = ['office', 'hybrid', 'remote']
const FSP_VALUES: readonly FspFilter[] = ['any', 'linked', 'prize']

export const DEFAULT_FILTERS: ScoutingFilters = {
  grades: [],
  skills: [],
  fsp: 'any',
  formats: [],
  confirmed_only: false,
  page: 1,
}

// --- param names (short, stable, documented in FE2.md) --------------------------

export const PARAM = {
  grades: 'grades',
  skills: 'skills',
  fsp: 'fsp',
  formats: 'formats',
  salary_max: 'salary_max',
  confirmed_only: 'confirmed_only',
  preset: 'preset',
  page: 'page',
  candidate: 'c',
} as const

// --- serialize / parse -----------------------------------------------------------

/** Serialize all scouting state (filters + page + drawer) into query params. */
export function serializeFilters(filters: ScoutingFilters): URLSearchParams {
  const p = new URLSearchParams()
  if (filters.grades.length) p.set(PARAM.grades, filters.grades.join(','))
  if (filters.skills.length) p.set(PARAM.skills, filters.skills.join(','))
  if (filters.fsp !== DEFAULT_FILTERS.fsp) p.set(PARAM.fsp, filters.fsp)
  if (filters.formats.length) p.set(PARAM.formats, filters.formats.join(','))
  if (typeof filters.salary_max === 'number') p.set(PARAM.salary_max, String(filters.salary_max))
  if (filters.confirmed_only) p.set(PARAM.confirmed_only, '1')
  if (filters.preset) p.set(PARAM.preset, filters.preset)
  if (filters.page > 1) p.set(PARAM.page, String(filters.page))
  if (filters.candidate) p.set(PARAM.candidate, filters.candidate)
  return p
}

function csv<T extends string>(raw: string | null, allowed?: readonly T[]): T[] {
  if (!raw) return []
  const parts = raw.split(',').map((s) => s.trim()).filter(Boolean)
  return allowed ? parts.filter((x): x is T => (allowed as readonly string[]).includes(x)) : (parts as T[])
}

/** Parse query params back into validated filters with defaults. Unknown or
 *  malformed values are dropped, never thrown — URLs are user-editable. */
export function parseFilters(params: URLSearchParams): ScoutingFilters {
  const salaryRaw = params.get(PARAM.salary_max)
  const salaryMax = salaryRaw !== null && /^\d+$/.test(salaryRaw) ? Number(salaryRaw) : undefined

  const pageRaw = params.get(PARAM.page)
  const page = pageRaw && /^\d+$/.test(pageRaw) ? Math.max(1, Number(pageRaw)) : 1

  const fspRaw = params.get(PARAM.fsp)
  const fsp: FspFilter = FSP_VALUES.includes(fspRaw as FspFilter) ? (fspRaw as FspFilter) : 'any'

  const candidate = params.get(PARAM.candidate) || undefined

  return {
    grades: csv<Grade>(params.get(PARAM.grades), GRADES),
    skills: csv(params.get(PARAM.skills)),
    fsp,
    formats: csv<WorkFormat>(params.get(PARAM.formats), FORMATS),
    ...(salaryMax !== undefined ? { salary_max: salaryMax } : {}),
    confirmed_only: params.get(PARAM.confirmed_only) === '1',
    preset: params.get(PARAM.preset) || undefined,
    page,
    candidate,
  }
}

/** Params that participate in filtering (everything except page/candidate). */
type FilterKeys = Omit<ScoutingFilters, 'page' | 'candidate'>

function sameFilters(a: FilterKeys, b: FilterKeys): boolean {
  return serializeFilters({ ...a, page: 1 }).toString() === serializeFilters({ ...b, page: 1 }).toString()
}

// --- hook ------------------------------------------------------------------------

/**
 * Binds `ScoutingFilters` to the browser URL via react-router's
 * `useSearchParams`. Query keys derived from these filters feed TanStack
 * Query through `usePositionPool` — no extra state layer needed: URL change →
 * new render → new queryKey → refetch.
 */
export function useScoutingUrlState(_positionId: string) {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo(() => parseFilters(searchParams), [searchParams])

  /** Replace the whole filter object; resets page unless only page changed. */
  const setFilters = useCallback(
    (next: Partial<ScoutingFilters>) => {
      setSearchParams(
        (prev) => {
          const current = parseFilters(prev)
          const withoutPageCandidate: ScoutingFilters = {
            ...current,
            ...next,
            page: next.page ?? current.page,
            candidate: next.candidate === undefined ? current.candidate : next.candidate,
          }
          // any filter change (not page-only) resets pagination
          const filterChanged = !sameFilters(current, withoutPageCandidate)
          const final: ScoutingFilters = {
            ...withoutPageCandidate,
            page: filterChanged ? 1 : withoutPageCandidate.page,
          }
          return serializeFilters(final)
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const setPage = useCallback((page: number) => setFilters({ page }), [setFilters])

  /** Open/close the drawer via `?c=`. */
  const setCandidate = useCallback(
    (publicId?: string) => setFilters({ candidate: publicId }),
    [setFilters],
  )

  const resetFilters = useCallback(() => {
    setSearchParams(() => serializeFilters({ ...DEFAULT_FILTERS }), { replace: true })
  }, [setSearchParams])

  return { filters, setFilters, setPage, setCandidate, resetFilters }
}
