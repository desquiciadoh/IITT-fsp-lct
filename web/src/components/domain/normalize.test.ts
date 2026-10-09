import { describe, it, expect } from 'vitest'
import { normalizeComponents } from '@/components/domain/normalize'

describe('normalizeComponents', () => {
  it('passes list shape through, deriving weights', () => {
    const out = normalizeComponents([
      { key: 'skill', contribution: 30 },
      { key: 'grade', contribution: 20 },
    ])
    expect(out).toEqual([
      { key: 'skill', contribution: 30, weight: 0.6 },
      { key: 'grade', contribution: 20, weight: 0.4 },
    ])
  })

  it('keeps provided weights in list shape', () => {
    const out = normalizeComponents([{ key: 'salary', contribution: 8, weight: 0.1 }])
    expect(out[0].weight).toBe(0.1)
  })

  it('converts dict shape to list with max-based weights', () => {
    const out = normalizeComponents({ skill: 30, grade: 20, strength: 10 })
    const byKey = Object.fromEntries(out.map((c) => [c.key, c]))
    expect(byKey.skill).toEqual({ key: 'skill', contribution: 30, weight: 0.35 })
    expect(byKey.grade).toEqual({ key: 'grade', contribution: 20, weight: 0.25 })
    expect(byKey.strength).toEqual({ key: 'strength', contribution: 10, weight: 0.15 })
    expect(out.reduce((s, c) => s + c.contribution, 0)).toBe(60)
  })

  it('keeps the fsp segment (dict has it, list contract does not)', () => {
    const out = normalizeComponents({ fsp: 12 })
    expect(out).toEqual([{ key: 'fsp', contribution: 12, weight: 0.15 }])
  })

  it('handles null/undefined/empty', () => {
    expect(normalizeComponents(undefined)).toEqual([])
    expect(normalizeComponents(null)).toEqual([])
    expect(normalizeComponents({})).toEqual([])
  })

  it('render-relevant invariant: both shapes produce comparable totals', () => {
    const dict = normalizeComponents({ skill: 30, grade: 20, fsp: 15 })
    const list = normalizeComponents([
      { key: 'skill', contribution: 30 },
      { key: 'grade', contribution: 20 },
      { key: 'fsp', contribution: 15 },
    ])
    const sum = (xs: { contribution: number }[]) =>
      xs.reduce((s, c) => s + c.contribution, 0)
    expect(sum(dict)).toBe(sum(list))
    expect(dict.map((c) => c.key).sort()).toEqual(list.map((c) => c.key).sort())
  })
})
