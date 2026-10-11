import { describe, expect, it } from 'vitest'
import type { PoolEntry, ScoreComponent } from '@/api/types'
import { PRESETS, isBalanced, rerank } from '@/features/scouting/pool-power/ranking'

function entry(score: number, components: ScoreComponent[]): PoolEntry {
  return {
    talent: { public_id: `p${score}` },
    score,
    components,
    reasons: [],
    shortlisted: false,
  } as unknown as PoolEntry
}

const ids = (rows: { entry: PoolEntry }[]) => rows.map((r) => r.entry.talent.public_id)

const SKILL_HEAVY = entry(60, [
  { key: 'skill', contribution: 40 },
  { key: 'grade', contribution: 10 },
  { key: 'salary', contribution: 10 },
])
const SALARY_HEAVY = entry(55, [
  { key: 'salary', contribution: 40 },
  { key: 'skill', contribution: 10 },
  { key: 'grade', contribution: 5 },
])

describe('isBalanced', () => {
  it('flags equal weights as balanced', () => {
    expect(isBalanced(PRESETS[0].weights)).toBe(true)
    expect(isBalanced({ ...PRESETS[0].weights, salary: 2 })).toBe(false)
  })
})

describe('rerank', () => {
  it('returns the original order unchanged for balanced weights', () => {
    const items = [SKILL_HEAVY, SALARY_HEAVY]
    const out = rerank(items, PRESETS[0].weights)
    expect(ids(out)).toEqual(['p60', 'p55'])
    expect(out[0].score).toBe(60)
  })

  it('skills preset lifts the skill-heavy candidate to the top', () => {
    const out = rerank([SKILL_HEAVY, SALARY_HEAVY], PRESETS[1].weights)
    expect(out[0].entry.talent.public_id).toBe('p60')
  })

  it('budget preset lifts the salary-heavy candidate to the top', () => {
    const out = rerank([SKILL_HEAVY, SALARY_HEAVY], PRESETS[2].weights)
    expect(out[0].entry.talent.public_id).toBe('p55')
  })

  it('contributions always sum to the shown score', () => {
    for (const preset of PRESETS) {
      const out = rerank([SKILL_HEAVY, SALARY_HEAVY], preset.weights)
      for (const row of out) {
        const sum = row.components.reduce((s, c) => s + c.contribution, 0)
        expect(Math.round(sum)).toBe(row.score)
      }
    }
  })

  it('reorders without mutating the input', () => {
    const items = [SALARY_HEAVY, SKILL_HEAVY]
    const out = rerank(items, PRESETS[2].weights)
    expect(out[0].entry).toBe(SALARY_HEAVY)
    expect(items[0]).toBe(SALARY_HEAVY)
  })
})