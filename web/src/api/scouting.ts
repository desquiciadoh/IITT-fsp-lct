/**
 * FE-10 · Scouting API layer.
 *
 * Hand-written TanStack Query hooks over `customFetch` (orval generates the
 * mutators but not the employer-side queries we need to widen). Every gap
 * this file works around is tagged: G7 (league shelves), G8 (pool filters /
 * facets / components dict), G9 (talent card sections), G16 (no shortlist
 * list endpoint).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  Grade,
  LeagueShelf,
  Position,
  PoolItemView,
  ScoutingFilters,
  ScoutingPoolResponse,
  Spec,
  TalentDetail,
  WorkFormat,
} from '@/api/types'

// --- query-param serialization ---------------------------------------------

/** Serialize scouting filters into URLSearchParams for the pool request. */
export function filterParams(filters: Pick<ScoutingFilters, 'grades' | 'skills' | 'fsp' | 'formats' | 'salary_max' | 'confirmed_only' | 'preset' | 'page'>): URLSearchParams {
  const p = new URLSearchParams()
  if (filters.grades.length) p.set('grades', filters.grades.join(','))
  if (filters.skills.length) p.set('skills', filters.skills.join(','))
  if (filters.fsp !== 'any') p.set('fsp', filters.fsp)
  if (filters.formats.length) p.set('formats', filters.formats.join(','))
  if (typeof filters.salary_max === 'number') p.set('salary_max', String(filters.salary_max))
  if (filters.confirmed_only) p.set('confirmed_only', '1')
  if (filters.preset) p.set('preset', filters.preset)
  if (filters.page > 1) p.set('page', String(filters.page))
  return p
}

// --- skill shape helpers (gap G8: `skills` is a flat string list today) -----

import type { PoolSkill, TalentShort, TalentShortView } from '@/api/types'

/** Read the name out of either served skill shape (`string` or `{name}`). */
export function skillName(s: string | PoolSkill): string {
  return typeof s === 'string' ? s : s.name
}

/**
 * Normalize skills to `{name, source}` objects. Until BE marks verification
 * per skill, we infer the source from the talent's reasons: a plus/minus
 * reason with `source: 'test'` mentions the skill → verified; otherwise the
 * skill stays self-reported (declared). Unknown strings default to declared.
 */
export function normalizeSkills(
  skills: (string | PoolSkill)[] | undefined,
  reasons?: { kind: string; text: string; source?: string }[],
): PoolSkill[] {
  if (!skills) return []
  const testText = (reasons ?? [])
    .filter((r) => r.source === 'test')
    .map((r) => r.text.toLowerCase())
    .join(' ')
  return skills.map((s) => {
    if (typeof s !== 'string') return { name: s.name, source: s.source }
    const verified = testText.includes(s.toLowerCase())
    return { name: s, source: verified ? 'test' : 'declared' }
  })
}

// --- client-side fallback (gap G8: backend ignores filters) ------------------

const GRADE_ORDER: Grade[] = ['intern', 'junior', 'middle', 'senior']

/**
 * Predicate used when the pool response carries no `facets` — i.e. the
 * server did not apply our filters (capability detection, not hardcoding).
 * Mirrors the semantics the BE will implement for G8.
 */
export function matchesPoolFilters(item: PoolItemView, f: ScoutingFilters): boolean {
  const t = item.talent
  if (f.grades.length) {
    const grade = t.league?.grade
    if (!grade || !f.grades.includes(grade)) return false
  }
  if (f.skills.length) {
    const owned = (t.skills ?? []).map((s) => skillName(s).toLowerCase())
    if (!f.skills.every((s) => owned.includes(s.toLowerCase()))) return false
  }
  if (f.fsp !== 'any') {
    const linked = Boolean(t.fsp?.linked)
    if (f.fsp === 'linked' && !linked) return false
    if (f.fsp === 'prize') {
      const best = (t.fsp?.best_tier ?? '').toLowerCase()
      if (!linked || !(best === 'gold' || best === 'silver' || best === 'bronze' || best === 'prize')) {
        return false
      }
    }
  }
  if (f.formats.length) {
    const formats = t.work_formats ?? []
    if (!f.formats.some((x: WorkFormat) => formats.includes(x))) return false
  }
  if (typeof f.salary_max === 'number') {
    const min = t.salary_min ?? 0
    if (min > f.salary_max) return false
  }
  if (f.confirmed_only && t.league?.status !== 'confirmed') return false
  return true
}

/** Adjacent-grade preset helper kept in one place for later reuse. */
export function expandGradePreset(grade: Grade, allowAdjacent: boolean): Grade[] {
  if (!allowAdjacent) return [grade]
  const i = GRADE_ORDER.indexOf(grade)
  if (i < 0) return [grade]
  return GRADE_ORDER.slice(Math.max(0, i - 1), Math.min(GRADE_ORDER.length, i + 2))
}

// --- hooks -------------------------------------------------------------------

/**
 * GET /api/leagues?specialization= → league shelves for the position's spec.
 * gap G7: real shape is mocked; today BE returns the candidate's own league.
 */
export function useLeagues(specialization?: Spec) {
  return useQuery({
    queryKey: keys.leagues(specialization),
    enabled: Boolean(specialization),
    staleTime: 5 * 60_000,
    queryFn: () => {
      const p = new URLSearchParams()
      if (specialization) p.set('specialization', specialization)
      return customFetch<{ items: LeagueShelf[] }>(`/api/leagues?${p.toString()}`)
    },
    select: (data) => data.items,
  })
}

/** GET /api/positions — employer dashboard/list source for the scouting header. */
export function usePositions() {
  return useQuery({
    queryKey: keys.positions,
    queryFn: () => customFetch<Position[]>('/api/positions'),
  })
}

/** GET /api/positions/{id} — header of the scouting screen. */
export function usePosition(id: string | undefined) {
  return useQuery({
    queryKey: keys.position(id ?? ''),
    enabled: Boolean(id),
    queryFn: () => customFetch<Position>(`/api/positions/${id}`),
  })
}

/**
 * GET /api/positions/{id}/pool with filters sent as query params.
 * gap G8: the backend ignores them and omits `facets`; when `facets` is
 * missing we mark the response and the UI applies `matchesPoolFilters`.
 */
export function usePositionPool(positionId: string | undefined, filters: ScoutingFilters) {
  return useQuery({
    queryKey: [...keys.pool(positionId ?? ''), keys.pool(positionId ?? ''), filterParams(filters).toString()],
    enabled: Boolean(positionId),
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const p = filterParams(filters)
      const qs = p.toString()
      const raw = await customFetch<ScoutingPoolResponse>(
        `/api/positions/${positionId}/pool${qs ? `?${qs}` : ''}`,
      )
      const serverFiltered = raw.facets !== undefined || raw.filters_applied === true
      const items = raw.items.map(normalizePoolItem)
      const filtered = serverFiltered ? items : items.filter((i) => matchesPoolFilters(i, filters))
      return {
        ...raw,
        items: filtered,
        total: serverFiltered ? raw.total : filtered.length,
        clientFiltered: !serverFiltered,
      } satisfies ScoutingPoolResponse & { clientFiltered: boolean }
    },
  })
}

/** Accept both component shapes (dict today, list tomorrow — gap G8). */
function normalizePoolItem(raw: PoolItemView): PoolItemView {
  const reasons = raw.reasons ?? []
  return {
    ...raw,
    // keep the components payload as-is; ScoreBar normalizes dict|list via
    // normalizeComponents() at render time (single normalization point)
    talent: { ...raw.talent, skills: normalizeSkills(raw.talent.skills, reasons) },
    reasons,
    gaps: raw.gaps ?? reasons.filter((r) => r.kind === 'minus').map((r) => r.text),
  }
}

/**
 * PUT/DELETE /api/positions/{id}/shortlist/{public_id} → 204.
 * Optimistic toggle; the tray survives filter changes because every pool
 * cache entry is patched (and toggling back on a filtered-out page still
 * works via the previous-response snapshot).
 * gap G16: no "list shortlist" endpoint — the tray is built from
 * `shortlisted: true` items across cached pool pages.
 */
export function useShortlistToggle(positionId: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ publicId, add }: { publicId: string; add: boolean }) => {
      const url = `/api/positions/${positionId}/shortlist/${publicId}`
      await customFetch<void>(url, { method: add ? 'PUT' : 'DELETE' })
    },
    onMutate: async ({ publicId, add }) => {
      await qc.cancelQueries({ queryKey: keys.pool(positionId) })
      const previous = qc.getQueriesData<ScoutingPoolResponse>({ queryKey: keys.pool(positionId) })
      qc.setQueriesData<ScoutingPoolResponse>(
        { queryKey: keys.pool(positionId) },
        (old) =>
          old
            ? {
                ...old,
                items: old.items.map((i) =>
                  i.talent.public_id === publicId ? { ...i, shortlisted: add } : i,
                ),
              }
            : old,
      )
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      ctx?.previous.forEach(([key, data]) => qc.setQueryData(key, data))
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.pool(positionId) })
    },
  })
}

/**
 * GET /api/talent/{public_id} — drawer payload (gap G9).
 * `contacts` is null until the company holds a grant; future sections are
 * hidden while absent. Skills are normalized to `{name, source}` here too,
 * so the drawer can split verified vs self-reported without string[] leaks.
 */
export function useTalent(publicId: string | undefined) {
  return useQuery({
    queryKey: keys.talent(publicId ?? ''),
    enabled: Boolean(publicId),
    staleTime: 60_000,
    queryFn: async () => {
      const raw = await customFetch<TalentDetail & TalentShort>(`/api/talent/${publicId}`)
      return {
        ...raw,
        skills: normalizeSkills(raw.skills as (string | PoolSkill)[] | undefined),
      } satisfies TalentDetail
    },
  })
}
