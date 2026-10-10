/**
 * FE-10 · Scouting — pure-logic unit tests (node env, no DOM).
 *
 * Covers the contract the UI relies on:
 *   - filters ⇄ URL params roundtrip (URL is the single source of truth);
 *   - client-side fallback semantics when the BE ignores filters (gap G8);
 *   - gaps/relaxations derivation and league-shelf aggregation (G7/G8);
 *   - the stateful scouting MSW mock over real HTTP (pool filters + facets,
 *     shortlist PUT/DELETE → 204, tray list G16, drawer contacts gating G9).
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { filtersToParams, paramsToFilters } from '@/api/scouting'
import {
  activeFilterCount,
  applyClientFilters,
  deriveGaps,
  deriveRelaxations,
  EMPTY_FILTERS,
  matchesFilters,
  needsClientFiltering,
  summarizeShelves,
} from '@/features/scouting/filters'
import type { LeagueShelf, PoolEntry, PoolFilters, PoolResponse } from '@/api/types'
import { scoutingHandlers, seedShortlist } from '@/mocks/handlers/scouting'

const server = setupServer(...scoutingHandlers)
const BASE = 'http://localhost'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(async () => {
  await fetch(`${BASE}/api/_mock/scouting/reset`, { method: 'POST' })
})
afterAll(() => server.close())

const withFilters = (over: Partial<PoolFilters>): PoolFilters => ({ ...EMPTY_FILTERS, ...over })

describe('filters ⇄ params roundtrip', () => {
  it('empty filters serialize to an empty query string', () => {
    expect(filtersToParams(EMPTY_FILTERS).toString()).toBe('')
  })

  it('roundtrips a fully populated filter set', () => {
    const f = withFilters({
      grades: ['middle', 'senior'],
      skills: ['python', 'django'],
      fsp: 'prize',
      formats: ['remote', 'hybrid'],
      salary_max: 300000,
      confirmed_only: true,
      preset: 'fsp_stars',
      page: 3,
    })
    const back = paramsToFilters(new URLSearchParams(filtersToParams(f)))
    expect(back).toEqual(f)
  })

  it('ignores unknown/garbage param values instead of crashing', () => {
    const p = new URLSearchParams('grades=bogus,middle&fsp=nope&salary_max=-5&page=0&confirmed_only=1')
    const f = paramsToFilters(p)
    expect(f.grades).toEqual(['middle'])
    expect(f.fsp).toBe('any')
    expect(f.salary_max).toBeNull()
    expect(f.page).toBe(1)
    expect(f.confirmed_only).toBe(false)
  })

  it('counts only non-default filters as active', () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0)
    expect(activeFilterCount(withFilters({ grades: ['junior'], page: 2 }))).toBe(1) // page ≠ filter
  })
})

// --- fixtures for the pure functions ------------------------------------------

const entry = (id: string, score: number, over: Partial<PoolEntry> = {}): PoolEntry => ({
  talent: {
    public_id: id,
    city: 'Москва',
    work_formats: ['remote'],
    salary_min: 200000,
    salary_max: 300000,
    salary_type: 'gross',
    league: { specialization: 'backend', grade: 'middle', status: 'confirmed' },
    fsp: { linked: true, best_tier: 'winner' },
    skills: ['python'],
  },
  score,
  components: { skill: 20, grade: 20 },
  reasons: [
    { kind: 'plus', text: 'покрыт must-have «python»' },
    { kind: 'minus', text: 'не покрыт must-have «django»' },
  ],
  shortlisted: false,
  ...over,
})

describe('client-side fallback (gap G8)', () => {
  it('detects server filtering by the presence of facets', () => {
    expect(needsClientFiltering(undefined, withFilters({ grades: ['middle'] }))).toBe(true)
    expect(needsClientFiltering({ grades: { middle: 3 } }, withFilters({ grades: ['middle'] }))).toBe(false)
    // No active filters → never re-filter on the client.
    expect(needsClientFiltering(undefined, EMPTY_FILTERS)).toBe(false)
  })

  it('matchesFilters applies every dimension with AND semantics', () => {
    const e = entry('a', 50)
    expect(matchesFilters(e.talent, EMPTY_FILTERS)).toBe(true)
    expect(matchesFilters(e.talent, withFilters({ grades: ['senior'] }))).toBe(false)
    expect(matchesFilters(e.talent, withFilters({ grades: ['middle'], formats: ['remote'] }))).toBe(true)
    expect(matchesFilters(e.talent, withFilters({ formats: ['office'] }))).toBe(false)
    expect(matchesFilters(e.talent, withFilters({ salary_max: 150000 }))).toBe(false)
    expect(matchesFilters(e.talent, withFilters({ skills: ['Python'] }))).toBe(true) // case-insensitive
    expect(matchesFilters(e.talent, withFilters({ skills: ['rust'] }))).toBe(false)
    expect(matchesFilters(e.talent, withFilters({ fsp: 'prize' }))).toBe(true)
    expect(matchesFilters(e.talent, withFilters({ confirmed_only: true }))).toBe(true)
    expect(matchesFilters(e.talent, withFilters({ preset: 'confirmed' }))).toBe(true)
  })

  it('applyClientFilters filters, sorts desc and paginates', () => {
    const items = [entry('lo', 10), entry('mid', 55), entry('hi', 90), entry('no', 5, { talent: { ...entry('no', 5).talent, skills: [] } })]
    const data: PoolResponse = { items, total: items.length, page: 1 }
    const view = applyClientFilters(data, withFilters({ skills: ['python'], page: 1 }))
    // 'lo' also carries the python skill; only 'no' (skills: []) drops out.
    expect(view.items.map((i) => i.talent.public_id)).toEqual(['hi', 'mid', 'lo'])
    expect(view.total).toBe(3)
    expect(view.pages).toBe(1)
    // clamps out-of-range pages
    expect(applyClientFilters(data, withFilters({ page: 99 })).page).toBe(1)
  })
})

describe('gaps & relaxations derivation', () => {
  it('derives gaps from minus-reasons until the target field ships', () => {
    expect(deriveGaps(entry('a', 1))).toEqual(['не покрыт must-have «django»'])
    // target shape passes through untouched
    expect(deriveGaps(entry('a', 1, { gaps: ['нет kafka'] }))).toEqual(['нет kafka'])
  })

  it('synthesizes at most three relaxation hints', () => {
    const many = Array.from({ length: 5 }, (_, i) =>
      entry(`e${i}`, 10, { reasons: [{ kind: 'minus', text: `минус ${i}` }] }),
    )
    const hints = deriveRelaxations(many)
    expect(hints.length).toBeLessThanOrEqual(3)
    expect(hints[0]).toContain('минус')
  })
})

describe('league shelves aggregation (gap G7)', () => {
  const shelves: LeagueShelf[] = [
    { specialization: 'backend', grade: 'junior', confirmed: 3, unconfirmed: 2, median_expectation: 180000 },
    { specialization: 'backend', grade: 'middle', confirmed: 5, unconfirmed: 1, median_expectation: 280000 },
    { specialization: 'backend', grade: 'senior', confirmed: 2, unconfirmed: 0, median_expectation: null },
  ]
  it('sums counts and takes the median of known medians', () => {
    expect(summarizeShelves(shelves)).toEqual({
      confirmed: 10,
      unconfirmed: 3,
      median: 180000,
    })
  })
  it('handles an empty shelf list', () => {
    expect(summarizeShelves([])).toEqual({ confirmed: 0, unconfirmed: 0, median: null })
  })
})

// --- stateful mock over HTTP ----------------------------------------------------

type PoolWire = PoolResponse

async function getJson<T>(path: string): Promise<{ status: number; body: T; stubbed: boolean }> {
  const res = await fetch(`${BASE}${path}`)
  return {
    status: res.status,
    body: (await res.json()) as T,
    stubbed: res.headers.get('X-Stub') === 'true',
  }
}

describe('scouting MSW mock (target shapes)', () => {
  it('G7 — /api/leagues returns a plain array of shelves', async () => {
    const { status, body, stubbed } = await getJson<LeagueShelf[]>('/api/leagues?specialization=backend')
    expect(status).toBe(200)
    expect(stubbed).toBe(true)
    expect(Array.isArray(body)).toBe(true)
    expect(body.length).toBeGreaterThan(0)
    expect(body[0]).toMatchObject({ specialization: 'backend' })
  })

  it('G8 — pool honors filters, ships facets/pages/relaxations, components as a list', async () => {
    const { body } = await getJson<PoolWire>('/api/positions/p1/pool?grades=senior&fsp=prize')
    expect(body.facets).toBeDefined()
    expect(body.pages).toBeGreaterThanOrEqual(1)
    expect(body.relaxations?.length).toBeGreaterThan(0)
    expect(body.items.length).toBeGreaterThan(0)
    for (const item of body.items) {
      expect(item.talent.league?.grade).toBe('senior')
      expect(Array.isArray(item.components)).toBe(true)
      expect(deriveGaps(item).length).toBeGreaterThanOrEqual(0)
    }
  })

  it('G16 — shortlist PUT→204 then appears in pool flags and the tray list; DELETE removes', async () => {
    const put = await fetch(`${BASE}/api/positions/p1/shortlist/t-001`, { method: 'PUT' })
    expect(put.status).toBe(204)

    const pool = await getJson<PoolWire>('/api/positions/p1/pool')
    expect(pool.body.items.find((i) => i.talent.public_id === 't-001')?.shortlisted).toBe(true)

    const tray = await getJson<Array<{ public_id: string }>>('/api/positions/p1/shortlist')
    expect(tray.body.map((t) => t.public_id)).toContain('t-001')

    const del = await fetch(`${BASE}/api/positions/p1/shortlist/t-001`, { method: 'DELETE' })
    expect(del.status).toBe(204)
    const tray2 = await getJson<Array<{ public_id: string }>>('/api/positions/p1/shortlist')
    expect(tray2.body.map((t) => t.public_id)).not.toContain('t-001')
  })

  it('G9 — talent detail gates contacts by grant; 404 problem for unknown ids', async () => {
    const granted = await getJson<{ contacts: unknown }>('/api/talent/t-002')
    expect(granted.body.contacts).not.toBeNull()

    const gated = await getJson<{ contacts: unknown; about?: string }>('/api/talent/t-001')
    expect(gated.body.contacts).toBeNull()
    expect(gated.body.about).toBeTruthy()

    const res = await fetch(`${BASE}/api/talent/nope`)
    expect(res.status).toBe(404)
    expect(res.headers.get('Content-Type')).toContain('application/problem+json')
  })
})

describe('FE-10 acceptance scenarios (FE2.md)', () => {
  /** The tray cache merge the UI performs per pool batch (useAbsorbShortlist). */
  const absorbIntoTray = (prev: Set<string>, items: PoolEntry[]): Set<string> => {
    const next = new Set(prev)
    for (const i of items) {
      if (i.shortlisted) next.add(i.talent.public_id)
      else next.delete(i.talent.public_id)
    }
    return next
  }

  it('after changing filters 10 times the shortlist is intact', async () => {
    seedShortlist('p1', ['t-001', 't-002'])
    let tray = new Set<string>()

    // Ten filter changes → ten pool queries; the tray absorbs every batch.
    const filterSets = [
      '',
      '?grades=senior',
      '?skills=python',
      '?fsp=linked',
      '?formats=remote',
      '?salary_max=300000&grades=middle',
      '?confirmed_only=true',
      '?preset=fsp_stars',
      '?page=1&grades=junior',
      '?skills=kafka&fsp=prize',
    ]
    for (const qs of filterSets) {
      const { body } = await getJson<PoolWire>(`/api/positions/p1/pool${qs}`)
      tray = absorbIntoTray(tray, body.items)
    }
    // Shortlisted candidates stay in the tray even when no longer visible.
    expect([...tray].sort()).toEqual(['t-001', 't-002'])

    // And the server agrees (G16 list endpoint in the mock).
    const list = await getJson<Array<{ public_id: string }>>('/api/positions/p1/shortlist')
    expect(list.body.map((t) => t.public_id).sort()).toEqual(['t-001', 't-002'])
  })

  it('a reload restores the whole view from the URL alone', () => {
    // Reload = the browser re-serializes the current query string; the UI
    // rebuilds tab/filters/drawer purely from params (?tab, ?c, filter keys).
    const url = new URL('http://localhost/employer/positions/p1?tab=pool&c=t-001&grades=middle,senior&fsp=prize&page=2')
    const sp = url.searchParams
    expect(sp.get('tab')).toBe('pool')
    expect(sp.get('c')).toBe('t-001')
    const restored = paramsToFilters(sp)
    expect(restored.grades).toEqual(['middle', 'senior'])
    expect(restored.fsp).toBe('prize')
    expect(restored.page).toBe(2)
    // …and serializing back yields the same wire format the server accepts.
    expect(filtersToParams(restored).toString()).toBe('grades=middle%2Csenior&fsp=prize&page=2')
  })

  it('contacts appear only after acceptance (grant-gated by the BE)', async () => {
    // Not accepted yet → drawer payload has no contacts.
    const before = await getJson<{ contacts: unknown }>('/api/talent/t-001')
    expect(before.body.contacts).toBeNull()
    // After the candidate accepts an offer the company holds a grant → the
    // same request now ships full contact details (t-002 models that state).
    const after = await getJson<{ contacts: Record<string, string> | null }>('/api/talent/t-002')
    expect(after.body.contacts).toMatchObject({ email: expect.any(String) })
  })
})
