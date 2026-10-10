import { describe, expect, it } from 'vitest'

import {
  DEFAULT_FILTERS,
  parseFilters,
  serializeFilters,
} from '@/features/scouting/url-state'
import type { ScoutingFilters } from '@/api/types'

const base = (over: Partial<ScoutingFilters> = {}): ScoutingFilters => ({
  ...DEFAULT_FILTERS,
  ...over,
})

describe('serializeFilters', () => {
  it('omits defaults — empty filters produce an empty query string', () => {
    expect(serializeFilters(base()).toString()).toBe('')
  })

  it('serializes every filter type', () => {
    const qs = serializeFilters(
      base({
        grades: ['middle', 'senior'],
        skills: ['python', 'kafka'],
        fsp: 'prize',
        formats: ['remote'],
        salary_max: 300000,
        confirmed_only: true,
        preset: 'adjacent',
        page: 3,
        candidate: 'A1B2C3',
      }),
    ).toString()
    expect(qs).toContain('grades=middle%2Csenior')
    expect(qs).toContain('skills=python%2Ckafka')
    expect(qs).toContain('fsp=prize')
    expect(qs).toContain('formats=remote')
    expect(qs).toContain('salary_max=300000')
    expect(qs).toContain('confirmed_only=1')
    expect(qs).toContain('preset=adjacent')
    expect(qs).toContain('page=3')
    expect(qs).toContain('c=A1B2C3')
  })

  it('drops page=1 and fsp=any (defaults)', () => {
    const qs = serializeFilters(base({ page: 1, fsp: 'any' })).toString()
    expect(qs).not.toContain('page')
    expect(qs).not.toContain('fsp')
  })
})

describe('parseFilters', () => {
  it('returns defaults for an empty query string', () => {
    expect(parseFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS)
  })

  it('round-trips a full state', () => {
    const original = base({
      grades: ['junior'],
      skills: ['django'],
      fsp: 'linked',
      formats: ['hybrid', 'office'],
      salary_max: 250000,
      confirmed_only: true,
      preset: 'must-skills',
      page: 2,
      candidate: 'X9Y8Z7',
    })
    expect(parseFilters(serializeFilters(original))).toEqual(original)
  })

  it('drops unknown grade/format/fsp values instead of throwing', () => {
    const p = new URLSearchParams('grades=wizard,middle&formats=mars,remote&fsp=nope')
    const f = parseFilters(p)
    expect(f.grades).toEqual(['middle'])
    expect(f.formats).toEqual(['remote'])
    expect(f.fsp).toBe('any')
  })

  it('falls back to defaults on malformed numbers', () => {
    const p = new URLSearchParams('salary_max=abc&page=-4')
    const f = parseFilters(p)
    expect(f.salary_max).toBeUndefined()
    expect(f.page).toBe(1)
  })

  it('clamps page < 1 to 1', () => {
    expect(parseFilters(new URLSearchParams('page=0')).page).toBe(1)
  })

  it('treats only "1" as confirmed_only=true', () => {
    expect(parseFilters(new URLSearchParams('confirmed_only=true')).confirmed_only).toBe(false)
    expect(parseFilters(new URLSearchParams('confirmed_only=1')).confirmed_only).toBe(true)
  })

  it('reads the drawer candidate from ?c=', () => {
    expect(parseFilters(new URLSearchParams('c=A1B2C3')).candidate).toBe('A1B2C3')
    expect(parseFilters(new URLSearchParams('c=')).candidate).toBeUndefined()
  })
})

describe('filter change resets page (hook semantics via pure helpers)', () => {
  // The hook's rule: any change to non-page params → page back to 1; a
  // page-only change keeps other params. We verify the primitives it uses.

  it('a new filter serialized over an old page-URL yields page=1', () => {
    const current = parseFilters(new URLSearchParams('grades=middle&page=4'))
    // simulate setFilters({ skills: ['python'] }) — page not in the patch
    const next = { ...current, skills: ['python'], page: 1 }
    const qs = serializeFilters(next).toString()
    expect(qs).not.toContain('page') // page=1 is default → omitted from the URL
    expect(parseFilters(new URLSearchParams(qs)).page).toBe(1)
  })

  it('a page-only change preserves all filters', () => {
    const current = parseFilters(
      new URLSearchParams('grades=senior&skills=kafka&fsp=prize&confirmed_only=1'),
    )
    const next = { ...current, page: 5 }
    const parsed = parseFilters(serializeFilters(next))
    expect(parsed.page).toBe(5)
    expect(parsed.grades).toEqual(current.grades)
    expect(parsed.skills).toEqual(current.skills)
    expect(parsed.fsp).toBe(current.fsp)
    expect(parsed.confirmed_only).toBe(true)
  })

  it('drawer toggle does not touch filters or page', () => {
    const current = parseFilters(new URLSearchParams('grades=middle&page=2&skills=python'))
    const next = { ...current, candidate: 'A1B2C3' }
    const parsed = parseFilters(serializeFilters(next))
    expect(parsed.candidate).toBe('A1B2C3')
    expect(parsed.page).toBe(2)
    expect(parsed.grades).toEqual(['middle'])
    expect(parsed.skills).toEqual(['python'])
  })
})
