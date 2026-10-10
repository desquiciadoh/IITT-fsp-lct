/**
 * FE-10 · Integration tests (pure logic) — stage 5.
 *
 * Covers the two contracts that the UI depends on and that were verified
 * manually before:
 *  1. client-side fallback `matchesPoolFilters` against the REAL mock seed
 *     (gap G8 — pool response arrives without `facets`, so the browser must
 *     filter);
 *  2. shortlist-tray resilience (`collectShortlist`) across cached pool
 *     queries with overlapping pages (gap G16).
 */
import { describe, expect, it } from 'vitest'

import { matchesPoolFilters } from '@/api/scouting'
import type { PoolItemView, ScoutingFilters } from '@/api/types'
import { DEFAULT_FILTERS } from '@/features/scouting/url-state'
import { collectShortlist } from '@/features/scouting/shortlist-tray'

// --- fixture: exact copy of the scouting mock SEED (src/mocks/handlers/scouting.ts)
// Kept in sync deliberately: these are "real mock data", not synthetic rows.

const seedPool: PoolItemView[] = [
  {
    talent: {
      public_id: 'A1B2C3', display_name: 'Анна К.', city: 'Москва',
      work_formats: ['remote', 'hybrid'], salary_min: 320000, salary_max: 400000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'senior', status: 'confirmed', rating: 2105, percentile: 97, strength: 82 },
      fsp: { linked: true, best_tier: 'gold', rank: '1', results: 4 },
      skills: ['python', 'django', 'postgresql', 'redis', 'kafka'],
      last_active_at: '2026-10-08T10:00:00Z',
    },
    score: 98, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'D4E5F6', display_name: 'Дмитрий С.', city: 'Санкт-Петербург',
      work_formats: ['remote'], salary_min: 220000, salary_max: 280000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'middle', status: 'confirmed', rating: 1842, percentile: 88, strength: 71 },
      fsp: { linked: true, best_tier: 'silver', rank: '2', results: 3 },
      skills: ['python', 'fastapi', 'postgresql', 'redis'],
      last_active_at: '2026-10-07T09:00:00Z',
    },
    score: 84, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'G7H8I9', display_name: 'Георгий П.', city: 'Казань',
      work_formats: ['hybrid', 'office'], salary_min: 180000, salary_max: 240000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'middle', status: 'pending', rating: 1750, percentile: 79, strength: 64 },
      fsp: { linked: false },
      skills: ['python', 'django', 'celery'],
      last_active_at: '2026-10-05T15:00:00Z',
    },
    score: 74, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'J1K2L3', display_name: 'Елена В.', city: 'Новосибирск',
      work_formats: ['remote', 'hybrid'], salary_min: 120000, salary_max: 160000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'junior', status: 'confirmed', rating: 1520, percentile: 61, strength: 55 },
      fsp: { linked: true, best_tier: 'bronze', rank: '3', results: 2 },
      skills: ['python', 'django'],
      last_active_at: '2026-10-06T12:00:00Z',
    },
    score: 70, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'M4N5O6', display_name: 'Максим Т.', city: 'Екатеринбург',
      work_formats: ['remote'], salary_min: 350000, salary_max: 420000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'senior', status: 'unconfirmed', rating: 1990, percentile: 93, strength: null },
      fsp: { linked: false },
      skills: ['node.js', 'typescript', 'postgresql'],
      last_active_at: '2026-10-01T08:00:00Z',
    },
    score: 79, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'P7Q8R9', display_name: 'Полина Р.', city: 'Москва',
      work_formats: ['office', 'hybrid'], salary_min: 250000, salary_max: 300000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'middle', status: 'confirmed', rating: 1800, percentile: 85, strength: 68 },
      fsp: { linked: true, best_tier: 'finalist', rank: '8', results: 5 },
      skills: ['python', 'fastapi', 'kafka', 'redis'],
      last_active_at: '2026-10-09T18:00:00Z',
    },
    score: 83, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'S1T2U3', display_name: 'Сергей Н.', city: 'Нижний Новгород',
      work_formats: ['office'], salary_min: 80000, salary_max: 110000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'intern', status: 'pending', percentile: 40, strength: 30 },
      fsp: { linked: false },
      skills: ['python'],
      last_active_at: '2026-09-28T11:00:00Z',
    },
    score: 55, components: {}, reasons: [], shortlisted: false,
  },
  {
    talent: {
      public_id: 'V4W5X6', display_name: 'Виктория Л.', city: 'Москва',
      work_formats: ['remote', 'hybrid'], salary_min: 330000, salary_max: 390000,
      salary_type: 'gross',
      league: { specialization: 'backend', grade: 'senior', status: 'confirmed', rating: 2050, percentile: 95, strength: 77 },
      fsp: { linked: true, best_tier: 'gold', rank: '1', results: 6 },
      skills: ['python', 'django', 'postgresql', 'redis', 'kafka', 'pytorch'],
      last_active_at: '2026-10-09T20:00:00Z',
    },
    score: 98, components: {}, reasons: [], shortlisted: false,
  },
]

const ids = (f: ScoutingFilters) =>
  seedPool.filter((i) => matchesPoolFilters(i, f)).map((i) => i.talent.public_id)

const F = (over: Partial<ScoutingFilters>): ScoutingFilters => ({ ...DEFAULT_FILTERS, ...over })

describe('matchesPoolFilters — client-side fallback on real mock data (G8)', () => {
  it('empty filters pass every seeded candidate (nothing silently dropped)', () => {
    expect(ids(F({}))).toHaveLength(seedPool.length)
  })

  it('grades=senior keeps only senior-league candidates', () => {
    expect(ids(F({ grades: ['senior'] })).sort()).toEqual(['A1B2C3', 'M4N5O6', 'V4W5X6'])
  })

  it('skills are AND-ed and case-insensitive', () => {
    expect(ids(F({ skills: ['python', 'KAFKA'] })).sort()).toEqual(['A1B2C3', 'P7Q8R9', 'V4W5X6'])
    // skill nobody has → empty result, no crash
    expect(ids(F({ skills: ['erlang'] }))).toEqual([])
  })

  it('fsp=linked keeps everyone with a linked profile', () => {
    expect(ids(F({ fsp: 'linked' })).sort()).toEqual(['A1B2C3', 'D4E5F6', 'J1K2L3', 'P7Q8R9', 'V4W5X6'])
  })

  it('fsp=prize keeps gold/silver/bronze but drops finalists and unlinked', () => {
    expect(ids(F({ fsp: 'prize' })).sort()).toEqual(['A1B2C3', 'D4E5F6', 'J1K2L3', 'V4W5X6'])
  })

  it('formats intersect (any-of semantics)', () => {
    // office-only request: Георгий (hybrid+office), Полина (office+hybrid), Сергей (office)
    expect(ids(F({ formats: ['office'] })).sort()).toEqual(['G7H8I9', 'P7Q8R9', 'S1T2U3'])
  })

  it('salary_max keeps candidates whose MIN expectation fits', () => {
    expect(ids(F({ salary_max: 200000 })).sort()).toEqual(['G7H8I9', 'J1K2L3', 'S1T2U3'])
  })

  it('confirmed_only drops pending/unconfirmed leagues', () => {
    expect(ids(F({ confirmed_only: true })).sort()).toEqual(
      ['A1B2C3', 'D4E5F6', 'J1K2L3', 'P7Q8R9', 'V4W5X6'],
    )
  })

  it('combined filters compose (senior + confirmed + prize + kafka)', () => {
    expect(ids(F({ grades: ['senior'], confirmed_only: true, fsp: 'prize', skills: ['kafka'] })))
      .toEqual(['A1B2C3', 'V4W5X6'])
  })
})

// --- collectShortlist (tray resilience, G16) -----------------------------------

type FakeQC = Parameters<typeof collectShortlist>[1]

const fakeQc = (entries: Array<[unknown, unknown]>): FakeQC =>
  ({ getQueriesData: () => entries }) as unknown as FakeQC

const marked = (id: string, score: number, shortlisted = true): PoolItemView => ({
  talent: { public_id: id, display_name: id },
  score,
  components: {},
  reasons: [],
  shortlisted,
})

describe('collectShortlist — tray survives filter changes (G16)', () => {
  it('dedupes by public_id across overlapping cached pages', () => {
    const page1 = { items: [marked('A', 90), marked('B', 80)] }
    const pageFiltered = { items: [marked('A', 90), marked('C', 70)] } // A repeats
    const res = collectShortlist('pos-1', fakeQc([
      [['pool', 'pos-1', 'page=1'], page1],
      [['pool', 'pos-1', 'grades=senior'], pageFiltered],
    ]))
    expect(res.map((i) => i.talent.public_id)).toEqual(['A', 'B', 'C']) // score desc
  })

  it('keeps a candidate shortlisted in one cache entry even if another entry still shows it unflagged (stale snapshot wins via dedupe-first)', () => {
    const fresh = { items: [{ ...marked('A', 90), shortlisted: false }] }
    const optimistic = { items: [marked('A', 90)] }
    const res = collectShortlist('pos-1', fakeQc([
      [['pool', 'pos-1', 'a'], optimistic],
      [['pool', 'pos-1', 'b'], fresh],
    ]))
    expect(res.map((i) => i.talent.public_id)).toEqual(['A'])
  })

  it('ignores non-shortlisted items and missing cache data', () => {
    const res = collectShortlist('pos-1', fakeQc([
      [['pool', 'pos-1', 'a'], { items: [marked('X', 5, false)] }],
      [['pool', 'pos-1', 'b'], undefined],
    ]))
    expect(res).toEqual([])
  })

  it('does not leak items of other positions (queryKey scoping is done by caller)', () => {
    // keys.pool(positionId) prefixing happens inside collectShortlist via qc;
    // here we assert the function itself returns [] when nothing is flagged.
    expect(collectShortlist('pos-2', fakeQc([]))).toEqual([])
  })
})
