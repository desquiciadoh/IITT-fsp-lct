import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  LeagueShelf,
  PoolEntry,
  PoolFilters,
  PoolResponse,
  Spec,
  TalentDetail,
  TalentSearchResponse,
  TalentShort,
} from '@/api/types'

/**
 * FE-10 · Scouting — API layer.
 *
 * Endpoints: GET /api/leagues?specialization= (gap G7),
 * GET /api/positions/{id}/pool (filters/facets/pagination are gap G8),
 * PUT/DELETE /api/positions/{id}/shortlist/{public_id},
 * GET /api/talent/{public_id} (drawer; sections are gap G9).
 * Missing pieces are mocked with MSW in their target shape (`X-Stub: true`),
 * so nothing changes when BE ships them.
 */

const GRADE_VALUES = ['intern', 'junior', 'middle', 'senior'] as const
const FORMAT_VALUES = ['office', 'hybrid', 'remote'] as const
const FSP_VALUES = ['any', 'linked', 'prize'] as const

/** Filters → query params. Empty/default values are omitted entirely. */
export function filtersToParams(f: PoolFilters): URLSearchParams {
  const p = new URLSearchParams()
  if (f.grades.length) p.set('grades', f.grades.join(','))
  if (f.skills.length) p.set('skills', f.skills.join(','))
  if (f.fsp !== 'any') p.set('fsp', f.fsp)
  if (f.formats.length) p.set('formats', f.formats.join(','))
  if (f.salary_max != null) p.set('salary_max', String(f.salary_max))
  if (f.confirmed_only) p.set('confirmed_only', 'true')
  if (f.preset) p.set('preset', f.preset)
  if (f.page > 1) p.set('page', String(f.page))
  return p
}

/** Query params → filters (URL is the single source of truth, FE-10). */
export function paramsToFilters(p: URLSearchParams): PoolFilters {
  const csv = (key: string) => (p.get(key) ? p.get(key)!.split(',').filter(Boolean) : [])
  const grades = csv('grades').filter((g): g is PoolFilters['grades'][number] =>
    (GRADE_VALUES as readonly string[]).includes(g),
  )
  const formats = csv('formats').filter((x): x is PoolFilters['formats'][number] =>
    (FORMAT_VALUES as readonly string[]).includes(x),
  )
  const fspRaw = p.get('fsp')
  const salaryRaw = Number(p.get('salary_max'))
  const pageRaw = Number(p.get('page'))
  return {
    grades,
    skills: csv('skills'),
    fsp: (FSP_VALUES as readonly string[]).includes(fspRaw ?? '')
      ? (fspRaw as PoolFilters['fsp'])
      : 'any',
    formats,
    salary_max: p.get('salary_max') && Number.isFinite(salaryRaw) && salaryRaw > 0 ? salaryRaw : null,
    confirmed_only: p.get('confirmed_only') === 'true',
    preset: p.get('preset') || null,
    page: Number.isFinite(pageRaw) && pageRaw > 0 ? Math.floor(pageRaw) : 1,
  }
}

export function useLeagues(specialization?: Spec) {
  return useQuery({
    queryKey: keys.leagues(specialization),
    queryFn: async () => {
      const qs = specialization ? `?specialization=${encodeURIComponent(specialization)}` : ''
      const data = await customFetch<LeagueShelf[] | { items?: LeagueShelf[] }>(
        `/api/leagues${qs}`,
      )
      // The backend returns a plain array (target shape); tolerate {items}.
      if (Array.isArray(data)) return data
      return data.items ?? []
    },
  })
}

/**
 * Ranked pool. The backend ignores filter params today (G8); whenever the
 * response has no `facets`, the caller applies the filters client-side as a
 * fallback (capability detection, not hardcoding — see applyClientFilters).
 */
export function usePool(positionId: string, filters: PoolFilters, enabled = true) {
  const query = filtersToParams(filters).toString()
  return useQuery({
    queryKey: keys.poolQuery(positionId, query),
    queryFn: () =>
      customFetch<PoolResponse>(
        `/api/positions/${positionId}/pool${query ? `?${query}` : ''}`,
      ),
    enabled: Boolean(positionId) && enabled,
  })
}

/**
 * Shortlist tray. gap G16: there is no "list shortlist" endpoint on the real
 * backend yet, so we build the tray from `shortlisted: true` pool items and
 * keep it in a cache that survives filter changes (entries accumulate across
 * queries). If/when the BE ships GET /api/positions/{id}/shortlist (the MSW
 * mock already serves the target shape), the same key refreshes from the
 * server — capability detection, not hardcoding.
 */
export function useShortlistTray(positionId: string) {
  const client = useQueryClient()

  /** Merge newly seen shortlisted entries into the tray cache. */
  const absorb = (items: PoolEntry[]) => {
    if (!positionId) return
    const seen = items.filter((i) => i.shortlisted).map((i) => i.talent)
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) => {
      const map = new Map<string, TalentShort>()
      for (const t of prev) map.set(t.public_id, t)
      for (const t of seen) map.set(t.public_id, t)
      return [...map.values()]
    })
  }

  /** Drop entries whose flag went false in the latest pool batch. */
  const reconcile = (items: PoolEntry[]) => {
    if (!positionId) return
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) => {
      let next = prev
      for (const i of items) {
        if (!i.shortlisted) next = next.filter((t) => t.public_id !== i.talent.public_id)
      }
      return next
    })
  }

  const remove = (publicId: string) => {
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) =>
      prev.filter((t) => t.public_id !== publicId),
    )
  }

  const tray = useQuery({
    queryKey: keys.shortlist(positionId),
    queryFn: async () => {
      try {
        // Gap G16 target shape: plain array of talents. Absent on the real
        // BE today → keep whatever the pool flags have accumulated.
        const data = await customFetch<TalentShort[]>(
          `/api/positions/${positionId}/shortlist`,
        )
        return Array.isArray(data) ? data : []
      } catch {
        return (
          client.getQueryData<TalentShort[]>(keys.shortlist(positionId)) ?? []
        )
      }
    },
    initialData: [] as TalentShort[],
    staleTime: Infinity, // the pool-driven cache is authoritative until G16 ships
    enabled: Boolean(positionId),
  })

  return { tray, absorb, reconcile, remove }
}

/** PUT /api/positions/{id}/shortlist/{public_id} → 204. Optimistic update. */
export function useToggleShortlist(positionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ publicId, add }: { publicId: string; add: boolean }) =>
      customFetch<void>(
        `/api/positions/${positionId}/shortlist/${encodeURIComponent(publicId)}`,
        { method: add ? 'PUT' : 'DELETE' },
      ),
    onMutate: async ({ publicId, add }) => {
      const shortlistKey = keys.shortlist(positionId)
      await client.cancelQueries({ queryKey: shortlistKey })
      const prev = client.getQueryData<PoolEntry['talent'][]>(shortlistKey) ?? []
      if (add) {
        const poolEntries = client.getQueriesData<PoolResponse>({ queryKey: keys.pool(positionId) })
        let talent: PoolEntry['talent'] | undefined
        for (const [, data] of poolEntries) {
          talent ??= data?.items.find((i) => i.talent.public_id === publicId)?.talent
        }
        if (talent && !prev.some((t) => t.public_id === talent.public_id)) {
          client.setQueryData(shortlistKey, [...prev, talent])
        }
      } else {
        client.setQueryData(
          shortlistKey,
          prev.filter((t) => t.public_id !== publicId),
        )
      }
      // Flip the flag in every cached pool page of this position too.
      client.setQueriesData<PoolResponse>({ queryKey: keys.pool(positionId) }, (data) =>
        data
          ? {
              ...data,
              items: data.items.map((i) =>
                i.talent.public_id === publicId ? { ...i, shortlisted: add } : i,
              ),
            }
          : data,
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) client.setQueryData(keys.shortlist(positionId), ctx.prev)
      void client.invalidateQueries({ queryKey: keys.pool(positionId) })
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: keys.pool(positionId) })
    },
  })
}

/** Candidate drawer payload: GET /api/talent/{public_id}. */
export function useTalent(publicId: string | null) {
  return useQuery({
    queryKey: keys.talent(publicId ?? ''),
    queryFn: () => customFetch<TalentDetail>(`/api/talent/${encodeURIComponent(publicId!)}`),
    enabled: Boolean(publicId),
  })
}

/**
 * FE-12 · GET /api/talent/search — plain talent search (no position context).
 * Same filter wire format as the pool (filtersToParams). The response shape is
 * {items: TalentShort[], total, page}; `pages`/`facets` are gaps G8/G14 — the
 * caller detects them and falls back to client-side filtering/facet counting.
 */
export function useTalentSearch(filters: PoolFilters, enabled = true) {
  const query = filtersToParams(filters).toString()
  return useQuery({
    queryKey: [...keys.talentSearch, query],
    queryFn: () =>
      customFetch<TalentSearchResponse>(`/api/talent/search${query ? `?${query}` : ''}`),
    enabled,
  })
}
