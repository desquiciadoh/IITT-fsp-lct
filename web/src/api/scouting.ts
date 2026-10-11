import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  LeagueShelf,
  PoolEntry,
  PoolFilters,
  PoolResponse,
  SalaryType,
  Spec,
  TalentDetail,
  TalentSearchResponse,
  TalentShort,
  WorkFormat,
} from '@/api/types'

/**
 * FE-10 · Scouting — API layer.
 *
 * Endpoints: GET /api/leagues?specialization=,
 * GET /api/positions/{id}/pool (server-side filters/facets/pagination —
 * G7/G8 shipped on the BE), PUT/DELETE /api/positions/{id}/shortlist/{public_id},
 * GET /api/talent/{public_id} (drawer; deep sections remain gap G9).
 * The `missing` MSW mode still serves these routes in the contract shape
 * (`X-Stub: true`) for backend-less demos; capability detection below stays
 * as defense-in-depth for older payloads.
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
 * Shortlist tray. GET /api/positions/{id}/shortlist is live on the BE (G16
 * shipped); additionally the tray accumulates `shortlisted: true` pool items
 * client-side so it survives filter changes between refreshes (entries merge
 * into the same query cache).
 */
export function talentDetailToShort(detail: TalentDetail): TalentShort {
  return {
    public_id: detail.public_id,
    display_name: detail.display_name,
    city: detail.city,
    work_formats: (detail.work_formats ?? []) as WorkFormat[],
    salary_min: detail.salary_min,
    salary_max: detail.salary_max,
    salary_type: (detail.salary_type as SalaryType) || undefined,
    league: detail.league,
    fsp: detail.fsp
      ? {
          linked: Boolean(detail.fsp.linked),
          best_tier: detail.fsp.best_tier,
          rank: detail.fsp.rank,
          results: detail.fsp.results,
        }
      : undefined,
    skills: (detail.skills ?? []).map((s) => (typeof s === 'string' ? s : s.name)),
  }
}

export type ToggleShortlistArgs = {
  publicId: string
  add: boolean
  talent?: TalentShort | TalentDetail
}

/**
 * Shortlist tray sync. The tray lives in the TanStack Query cache keyed by
 * position; pool batches merge their `shortlisted: true` entries into it and
 * GET /api/positions/{id}/shortlist refreshes the same key from the server.
 */
export function useShortlistTray(positionId: string) {
  const client = useQueryClient()

  /** Merge newly seen shortlisted entries into the tray cache. */
  const absorb = (items: PoolEntry[]) => {
    if (!positionId) return
    const seen = (items ?? []).filter((i) => i.shortlisted).map((i) => i.talent)
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) => {
      const map = new Map<string, TalentShort>()
      for (const t of prev ?? []) map.set(t.public_id, t)
      for (const t of seen) map.set(t.public_id, t)
      return [...map.values()]
    })
  }

  /** Drop entries whose flag went false in the latest pool batch. */
  const reconcile = (items: PoolEntry[]) => {
    if (!positionId) return
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) => {
      let next = prev ?? []
      for (const i of items ?? []) {
        if (!i.shortlisted) next = next.filter((t) => t.public_id !== i.talent.public_id)
      }
      return next
    })
  }

  const remove = (publicId: string) => {
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) =>
      (prev ?? []).filter((t) => t.public_id !== publicId),
    )
  }

  const tray = useQuery({
    queryKey: keys.shortlist(positionId),
    queryFn: async () => {
      try {
        const data = await customFetch<TalentShort[] | { items?: TalentShort[] }>(
          `/api/positions/${positionId}/shortlist`,
        )
        if (Array.isArray(data)) return data
        if (data && Array.isArray((data as { items?: TalentShort[] }).items)) {
          return (data as { items: TalentShort[] }).items
        }
        return []
      } catch {
        return (
          client.getQueryData<TalentShort[]>(keys.shortlist(positionId)) ?? []
        )
      }
    },
    staleTime: 30_000,
    enabled: Boolean(positionId),
  })

  return { tray, absorb, reconcile, remove }
}

/** PUT /api/positions/{id}/shortlist/{public_id} → 204. Optimistic update. */
export function useToggleShortlist(positionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ publicId, add }: ToggleShortlistArgs) =>
      customFetch<void>(
        `/api/positions/${positionId}/shortlist/${encodeURIComponent(publicId)}`,
        { method: add ? 'PUT' : 'DELETE' },
      ),
    onMutate: async ({ publicId, add, talent: passedTalent }) => {
      const shortlistKey = keys.shortlist(positionId)
      await client.cancelQueries({ queryKey: shortlistKey })
      const prev = client.getQueryData<TalentShort[]>(shortlistKey) ?? []
      if (add) {
        let talent: TalentShort | undefined = passedTalent
          ? ('contacts' in passedTalent || 'about' in passedTalent
              ? talentDetailToShort(passedTalent as TalentDetail)
              : (passedTalent as TalentShort))
          : undefined
        if (!talent) {
          const poolEntries = client.getQueriesData<PoolResponse>({
            queryKey: ['pool', positionId, 'query'],
          })
          for (const [, data] of poolEntries) {
            talent ??= data?.items?.find((i) => i.talent.public_id === publicId)?.talent
          }
        }
        if (!talent) {
          const searchEntries = client.getQueriesData<TalentSearchResponse>({
            queryKey: keys.talentSearch,
          })
          for (const [, data] of searchEntries) {
            talent ??= data?.items?.find((t) => t.public_id === publicId)
          }
        }
        if (!talent) {
          const detail = client.getQueryData<TalentDetail>(keys.talent(publicId))
          if (detail) {
            talent = talentDetailToShort(detail)
          }
        }
        if (talent && !prev.some((t) => t.public_id === talent!.public_id)) {
          client.setQueryData(shortlistKey, [...prev, talent])
        }
      } else {
        client.setQueryData(
          shortlistKey,
          prev.filter((t) => t.public_id !== publicId),
        )
      }
      // Flip the flag in every cached pool page of this position (queryKey prefix ['pool', positionId, 'query']).
      client.setQueriesData<PoolResponse>(
        { queryKey: ['pool', positionId, 'query'] },
        (data) =>
          data && Array.isArray(data.items)
            ? {
                ...data,
                items: data.items.map((i) =>
                  i.talent.public_id === publicId ? { ...i, shortlisted: add } : i,
                ),
              }
            : data,
      )
      // Flip the flag in search cache if present.
      client.setQueriesData<TalentSearchResponse>(
        { queryKey: keys.talentSearch },
        (data) =>
          data && Array.isArray(data.items)
            ? {
                ...data,
                items: data.items.map((i) =>
                  i.public_id === publicId ? { ...i, shortlisted: add } : i,
                ),
              }
            : data,
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) client.setQueryData(keys.shortlist(positionId), ctx.prev)
      void client.invalidateQueries({ queryKey: ['pool', positionId, 'query'] })
      void client.invalidateQueries({ queryKey: keys.shortlist(positionId) })
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['pool', positionId, 'query'] })
      void client.invalidateQueries({ queryKey: keys.shortlist(positionId) })
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
 * Same filter wire format as the pool (filtersToParams). The response is
 * {items, total, page, pages?, facets?}; when a deployment omits
 * `pages`/`facets`, the caller detects it and falls back to client-side
 * filtering/facet counting (defense-in-depth for older payloads).
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
