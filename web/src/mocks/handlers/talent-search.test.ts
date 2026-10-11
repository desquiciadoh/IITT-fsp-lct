/**
 * FE-12 · Talent search — tests.
 *
 * Pure logic (features/talent/search.ts):
 *   - isPrizeWinner across both `fsp` wire shapes (best_tier vs the real BE
 *     {results_count, sports_rank} payload);
 *   - client-side facet counting while the server omits them (G8);
 *   - matchesSearchFilters / applyClientSearch (filter → paginate);
 *   - resolveFacets capability detection (server facets win).
 *
 * Wire contract (stateful MSW mock, node env, same handlers as mocks/server.ts):
 *   - GET /api/talent/search returns {items,total,page,pages,facets};
 *   - the acceptance filter combo "prize winners + stack" (fsp=prize &
 *     skills=python,django) yields exactly the seeded prize winners with
 *     django in their verified stack;
 *   - pagination + CSV filters behave like the pool (shared wire format).
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { scoutingHandlers } from './scouting'
import type { PoolFilters, TalentSearchResponse, TalentShort } from '@/api/types'
import { filtersToParams } from '@/api/scouting'
import { EMPTY_FILTERS } from '@/features/scouting/filters'
import {
  applyClientSearch,
  computeClientFacets,
  isPrizeWinner,
  matchesSearchFilters,
  resolveFacets,
} from '@/features/talent/search'

const BASE = 'http://localhost'
const server = setupServer(...scoutingHandlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())

async function req<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  return (await res.json()) as T
}

const talent = (over: Partial<TalentShort>): TalentShort => ({ public_id: 'x', ...over })

// --- pure logic ---------------------------------------------------------------

describe('isPrizeWinner', () => {
  it('uses best_tier when present (mock/target shape)', () => {
    expect(isPrizeWinner(talent({ fsp: { linked: true, best_tier: 'winner' } }))).toBe(true)
    expect(isPrizeWinner(talent({ fsp: { linked: true, best_tier: 'finalist' } }))).toBe(false)
  })

  it('falls back to results_count + sports_rank (current BE shape)', () => {
    expect(
      isPrizeWinner(
        Object.assign(talent({}), {
          fsp: { linked: true, results_count: 3, sports_rank: 'kms' },
        }) as TalentShort,
      ),
    ).toBe(true)
    expect(
      isPrizeWinner(
        Object.assign(talent({}), {
          fsp: { linked: true, results_count: 0, sports_rank: 'kms' },
        }) as TalentShort,
      ),
    ).toBe(false)
  })

  it('never prizes an unlinked profile', () => {
    expect(isPrizeWinner(talent({ fsp: { linked: false } }))).toBe(false)
    expect(isPrizeWinner(talent({}))).toBe(false)
  })
})

describe('computeClientFacets', () => {
  const items: TalentShort[] = [
    talent({
      public_id: 'a',
      league: { grade: 'middle', status: 'confirmed' } as TalentShort['league'],
      work_formats: ['remote'],
      fsp: { linked: true, best_tier: 'winner' },
      skills: ['python'],
    }),
    talent({
      public_id: 'b',
      league: { grade: 'senior', status: 'unconfirmed' } as TalentShort['league'],
      work_formats: ['remote', 'office'],
      fsp: { linked: false },
      skills: ['go'],
    }),
  ]

  it('counts grades/formats/fsp/confirmed from the returned page', () => {
    const f = computeClientFacets(items)
    expect(f.grades).toEqual({ middle: 1, senior: 1 })
    expect(f.formats).toEqual({ remote: 2, office: 1 })
    expect(f.fsp).toEqual({ linked: 1, prize: 1 })
    expect(f.confirmed_only).toEqual({ true: 1 })
  })
})

describe('matchesSearchFilters & applyClientSearch', () => {
  const prizeWithStack = talent({
    public_id: 'p1',
    league: { grade: 'senior', status: 'confirmed' } as TalentShort['league'],
    fsp: { linked: true, best_tier: 'prize_winner' },
    skills: ['python', 'fastapi'],
    salary_min: 300000,
  })
  const winnerNoStack = talent({
    public_id: 'p2',
    league: { grade: 'middle', status: 'confirmed' } as TalentShort['league'],
    fsp: { linked: true, best_tier: 'winner' },
    skills: ['python', 'django'],
    salary_min: 260000,
  })
  const plain = talent({
    public_id: 'n1',
    league: { grade: 'junior', status: 'unconfirmed' } as TalentShort['league'],
    fsp: { linked: false },
    skills: ['python', 'django'],
    salary_min: 150000,
  })

  it('fsp=prize AND skills=python,django keeps only prize winners with the stack', () => {
    const f: PoolFilters = { ...EMPTY_FILTERS, fsp: 'prize', skills: ['python', 'django'] }
    const kept = [prizeWithStack, winnerNoStack, plain].filter((t) => matchesSearchFilters(t, f))
    expect(kept.map((t) => t.public_id)).toEqual(['p2'])
  })

  it('preset fsp_stars matches the same semantics as fsp=prize', () => {
    const f: PoolFilters = { ...EMPTY_FILTERS, preset: 'fsp_stars' }
    const kept = [prizeWithStack, winnerNoStack, plain].filter((t) => matchesSearchFilters(t, f))
    expect(kept.map((t) => t.public_id)).toEqual(['p1', 'p2'])
  })

  it('applies pagination over the filtered set (POOL_PAGE_SIZE)', () => {
    const many = Array.from({ length: 25 }, (_, i) =>
      talent({ public_id: `m${i}`, skills: ['python'] }),
    )
    const data: TalentSearchResponse = { items: many, total: many.length, page: 1 }
    const f: PoolFilters = { ...EMPTY_FILTERS, skills: ['python'], page: 2 }
    const view = applyClientSearch(data, f)
    expect(view.total).toBe(25)
    expect(view.pages).toBe(2)
    expect(view.page).toBe(2)
    expect(view.items.length).toBe(5)
  })

  it('clamps out-of-range pages instead of returning empty', () => {
    const data: TalentSearchResponse = { items: [plain], total: 1, page: 1 }
    const view = applyClientSearch(data, { ...EMPTY_FILTERS, page: 9 })
    expect(view.page).toBe(1)
    expect(view.items.length).toBe(1)
  })
})

describe('resolveFacets (capability detection)', () => {
  it('server facets win when present', () => {
    const data: TalentSearchResponse = {
      items: [],
      total: 0,
      page: 1,
      facets: { grades: { senior: 42 } },
    }
    expect(resolveFacets(data, [])).toEqual({ grades: { senior: 42 } })
  })

  it('falls back to client counting when absent', () => {
    const item = talent({
      league: { grade: 'middle', status: 'confirmed' } as TalentShort['league'],
    })
    const data: TalentSearchResponse = { items: [item], total: 1, page: 1 }
    expect(resolveFacets(data, [item])?.grades).toEqual({ middle: 1 })
  })

  it('undefined before the first response', () => {
    expect(resolveFacets(undefined, [])).toBeUndefined()
  })
})

// --- wire contract (MSW) --------------------------------------------------------

describe('GET /api/talent/search (mock ↔ target contract)', () => {
  it('no filters → whole seed with facets/pages metadata', async () => {
    const body = await req<TalentSearchResponse>('/api/talent/search')
    expect(body.total).toBe(6)
    expect(body.pages).toBe(1)
    expect(body.facets?.fsp.prize).toBe(3)
  })

  it('acceptance: prize winners + python/django stack', async () => {
    const f: PoolFilters = { ...EMPTY_FILTERS, fsp: 'prize', skills: ['python', 'django'] }
    const qs = filtersToParams(f).toString()
    const body = await req<TalentSearchResponse>(`/api/talent/search?${qs}`)
    // t-001 is the only prize winner carrying BOTH python and django
    // (t-002 → fastapi/kafka, t-005 → react). Skills chips are AND-of-stack.
    expect(body.items.map((t) => t.public_id)).toEqual(['t-001'])
    expect(body.total).toBe(1)
  })

  it('CSV filters compose: grades=senior&confirmed_only=true', async () => {
    const body = await req<TalentSearchResponse>(
      '/api/talent/search?grades=senior&confirmed_only=true',
    )
    expect(body.items.map((t) => t.public_id)).toEqual(['t-002'])
  })

  it('salary_max excludes pricier candidates', async () => {
    const body = await req<TalentSearchResponse>('/api/talent/search?salary_max=200000')
    expect(body.items.every((t) => (t.salary_min ?? 0) <= 200000)).toBe(true)
    expect(body.total).toBe(2)
  })

  it('search route is not swallowed by /api/talent/:publicId', async () => {
    // If wildcard ordering regressed, this would answer 404 problem+json.
    const res = await fetch(`${BASE}/api/talent/search`)
    expect(res.status).toBe(200)
    expect(res.headers.get('X-Stub')).toBe('true')
  })
})
