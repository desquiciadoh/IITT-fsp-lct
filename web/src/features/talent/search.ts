import type {
  Grade,
  PoolFilters,
  TalentSearchResponse,
  TalentShort,
  WorkFormat,
} from '@/api/types'
import { POOL_PAGE_SIZE } from '@/features/scouting/filters'

/**
 * FE-12 · Talent search (`/employer/talent`) — pure logic.
 *
 * Reuses the FE-10 filter model (PoolFilters ⇄ URL params) and its matching
 * semantics; this module adds what plain search needs on top of it:
 *   - client-side facet counting when the server omits `facets`;
 *   - a prize-detection fallback for backends whose `fsp` payload has no
 *     `best_tier` (the real BE serializer ships {linked, results_count,
 *     sports_rank});
 *   - the filter → paginate pipeline over raw TalentShort[] items (no score).
 * Capability detection everywhere: when the response carries `facets`, the
 * server did the work and we render its answer untouched.
 */

const PRIZE_TIERS = ['winner', 'prize_winner']

/**
 * Is this talent an FSP prize-winner? Primary signal is `best_tier` (mock /
 * target shape); fallback for the current backend payload: linked + at least
 * one verified result + a sports rank. Detect, never hardcode.
 */
export function isPrizeWinner(talent: TalentShort): boolean {
  const fsp = talent.fsp as
    | {
        linked?: boolean
        best_tier?: string
        results?: number
        results_count?: number
        sports_rank?: string | null
        rank?: string | null
      }
    | undefined
  if (!fsp?.linked) return false
  if (fsp.best_tier != null) return PRIZE_TIERS.includes(fsp.best_tier)
  const results = fsp.results ?? fsp.results_count ?? 0
  const rank = fsp.sports_rank ?? fsp.rank
  return results > 0 && Boolean(rank)
}

type RawFsp = { linked?: boolean; best_tier?: string; rank?: string; results?: number }

/** Normalize the two wire shapes of `fsp` into one badge-friendly object. */
export function normalizeFsp(raw: unknown): RawFsp | null {
  if (!raw || typeof raw !== 'object') return null
  const f = raw as RawFsp & { results_count?: number; sports_rank?: string | null }
  return {
    linked: Boolean(f.linked),
    best_tier: f.best_tier,
    rank: f.rank ?? f.sports_rank ?? undefined,
    results: f.results ?? f.results_count,
  }
}

/**
 * Facet counts computed on the client from the returned page — used when a
 * payload omits `facets` (defense-in-depth; G8 ships them server-side).
 * Shape mirrors the pool facets: {grades:{...}, formats:{...},
 * fsp:{linked,prize}, confirmed_only:{true:N}} so FilterPanel can consume
 * either source.
 */
export function computeClientFacets(
  items: TalentShort[],
): Record<string, Record<string, number>> {
  const bump = (bag: Record<string, number>, key?: string | null) => {
    if (key) bag[key] = (bag[key] ?? 0) + 1
  }
  const grades: Record<string, number> = {}
  const formats: Record<string, number> = {}
  const fsp: Record<string, number> = {}
  const confirmed: Record<string, number> = {}
  for (const t of items) {
    bump(grades, t.league?.grade)
    for (const f of t.work_formats ?? []) bump(formats, f)
    if (t.fsp?.linked) {
      fsp.linked = (fsp.linked ?? 0) + 1
      if (isPrizeWinner(t)) fsp.prize = (fsp.prize ?? 0) + 1
    }
    if (t.league?.status === 'confirmed') {
      confirmed.true = (confirmed.true ?? 0) + 1
    }
  }
  return { grades, formats, fsp, confirmed_only: confirmed }
}

/**
 * Search variant of matchesFilters (FE-10): same semantics, but prize
 * detection goes through isPrizeWinner() so both `fsp` wire shapes work.
 */
export function matchesSearchFilters(talent: TalentShort, f: PoolFilters): boolean {
  const league = talent.league
  if (f.grades.length && !f.grades.includes((league?.grade ?? '') as Grade)) return false
  if (f.confirmed_only && league?.status !== 'confirmed') return false
  if (f.preset === 'confirmed' && league?.status !== 'confirmed') return false
  if (
    f.formats.length &&
    !(talent.work_formats ?? []).some((x) => f.formats.includes(x as WorkFormat))
  ) {
    return false
  }
  if (f.salary_max != null && (talent.salary_min ?? Infinity) > f.salary_max) return false
  if (f.skills.length) {
    // skills is string[] in the search payload; tolerate {name} objects too.
    const names = (talent.skills ?? []).map((s: unknown) =>
      String(typeof s === 'string' ? s : ((s as { name?: string }).name ?? '')).toLowerCase(),
    )
    // AND across chips — same semantics as the BE pool selector and FE-10's
    // matchesFilters (see there for the rationale).
    if (!f.skills.every((skill) => names.includes(skill.toLowerCase()))) return false
  }
  if (f.fsp === 'linked' && !talent.fsp?.linked) return false
  if (f.fsp === 'prize' && !isPrizeWinner(talent)) return false
  if (f.preset === 'fsp_stars' && !isPrizeWinner(talent)) return false
  return true
}

/**
 * Fallback pipeline over raw talents: filter → paginate (POOL_PAGE_SIZE, the
 * same page size as the pool), mirroring the server contract.
 */
export function applyClientSearch(
  data: Pick<TalentSearchResponse, 'items' | 'total' | 'page'> | undefined,
  filters: PoolFilters,
): { items: TalentShort[]; total: number; page: number; pages: number } {
  const items = (data?.items ?? []).filter((t) => matchesSearchFilters(t, filters))
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

/**
 * Which facets to show in FilterPanel: server facets win when present
 * (capability detection); otherwise count them from the returned batch.
 */
export function resolveFacets(
  data: TalentSearchResponse | undefined,
  visibleItems: TalentShort[],
): Record<string, Record<string, number>> | undefined {
  if (data?.facets) return data.facets
  if (!data) return undefined
  return computeClientFacets(visibleItems)
}
