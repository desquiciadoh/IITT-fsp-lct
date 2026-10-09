import { describe, expect, it } from 'vitest'
import {
  PRESETS,
  normalizeWeights,
  rankedPool,
  weightedScore,
} from '@/features/pool/rank'
import type { PoolCandidate } from '@/api/types'

const skillFirst: PoolCandidate = {
  public_id: 'c-cand-a',
  display_name: 'Андрей',
  skills: ['Python'],
  components: { skill: 60, grade: 20, salary: 20 },
  score: 0,
  accept_likelihood: 'high',
  declared_salary_min: 200000,
}

const salaryFirst: PoolCandidate = {
  public_id: 'c-cand-b',
  display_name: 'Борис',
  skills: ['Go'],
  components: { skill: 10, grade: 10, salary: 70 },
  score: 0,
  accept_likelihood: 'low',
  declared_salary_min: 120000,
}

describe('rankedPool (FE-17)', () => {
  it('reorders when weights change from balanced to budget', () => {
    const balanced = rankedPool([skillFirst, salaryFirst], PRESETS.balanced)
    const budget = rankedPool([skillFirst, salaryFirst], PRESETS.budget)
    expect(balanced[0].candidate.public_id).toBe('c-cand-a')
    expect(budget[0].candidate.public_id).toBe('c-cand-b')
  })

  it('contributions sum to the shown score', () => {
    const items = rankedPool([skillFirst], PRESETS.skills)
    const item = items[0]
    const sum = Object.values(item.components).reduce((acc, v) => acc + (v ?? 0), 0)
    expect(sum).toBeCloseTo(item.score, 1)
  })

  it('normaliseWeights keeps a live slider sum to 1', () => {
    const weights = normalizeWeights({ skill: 0.6, salary: 0.6 })
    const total = Object.values(weights).reduce((acc, v) => acc + (v ?? 0), 0)
    expect(total).toBeCloseTo(1, 2)
  })

  it('weightedScore clamps to 100', () => {
    expect(weightedScore({ skill: 90, salary: 90 }, { skill: 1, salary: 0 })).toBeLessThanOrEqual(100)
  })
})