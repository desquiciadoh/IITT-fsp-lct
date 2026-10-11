import { describe, expect, it } from 'vitest'
import type { ValidationSystem } from '@/api/types'
import {
  confusionCells,
  formatDateTime,
  formatMillis,
  formatPercent,
  heatIntensity,
  leakRows,
  maxCell,
  sortSystems,
  tifPoints,
} from '@/features/lab/report'

const system = (name: string, ndcg10: number, p10 = 0): ValidationSystem => ({
  name,
  ndcg10,
  p10,
  r50: 0,
  mrr: 0,
})

describe('maxCell', () => {
  it('returns 0 for empty or undefined matrices', () => {
    expect(maxCell(undefined)).toBe(0)
    expect(maxCell([])).toBe(0)
    expect(maxCell([[], []])).toBe(0)
  })

  it('finds the largest finite cell', () => {
    expect(maxCell([[1, 9], [3, 4]])).toBe(9)
  })
})

describe('confusionCells', () => {
  it('flattens the matrix with row/col indices', () => {
    expect(confusionCells([[1, 2], [3, 4]])).toEqual([
      { row: 0, col: 0, value: 1 },
      { row: 0, col: 1, value: 2 },
      { row: 1, col: 0, value: 3 },
      { row: 1, col: 1, value: 4 },
    ])
  })

  it('tolerates missing rows', () => {
    expect(confusionCells(undefined)).toEqual([])
  })
})

describe('heatIntensity', () => {
  it('clamps to the 0..1 range', () => {
    expect(heatIntensity(5, 10)).toBe(0.5)
    expect(heatIntensity(20, 10)).toBe(1)
  })

  it('returns 0 for non-positive or non-finite inputs', () => {
    expect(heatIntensity(0, 10)).toBe(0)
    expect(heatIntensity(-1, 10)).toBe(0)
    expect(heatIntensity(5, 0)).toBe(0)
    expect(heatIntensity(Number.NaN, 10)).toBe(0)
  })
})

describe('tifPoints', () => {
  it('pairs theta and info up to the shorter array', () => {
    expect(tifPoints({ theta: [-1, 0, 1], info: [1, 2] })).toEqual([
      { theta: -1, info: 1 },
      { theta: 0, info: 2 },
    ])
  })

  it('returns an empty list when undefined', () => {
    expect(tifPoints(undefined)).toEqual([])
  })
})

describe('leakRows', () => {
  it('sorts by leak share without mutating the input', () => {
    const input = [
      { leak_share: 0.5, static_dtheta: 0, parametric_dtheta: 0 },
      { leak_share: 0.1, static_dtheta: 0, parametric_dtheta: 0 },
    ]
    const sorted = leakRows(input)
    expect(sorted.map((p) => p.leak_share)).toEqual([0.1, 0.5])
    expect(input[0].leak_share).toBe(0.5)
  })
})

describe('sortSystems', () => {
  it('orders by nDCG desc, then P@10 desc, then name', () => {
    const sorted = sortSystems([
      system('b', 0.5, 0.2),
      system('a', 0.5, 0.2),
      system('best', 0.9),
      system('weak', 0.1),
    ])
    expect(sorted.map((s) => s.name)).toEqual(['best', 'a', 'b', 'weak'])
  })

  it('handles undefined input', () => {
    expect(sortSystems(undefined)).toEqual([])
  })
})

describe('formatters', () => {
  it('formats percentages and handles gaps', () => {
    expect(formatPercent(0.5)).toBe('50.0%')
    expect(formatPercent(1)).toBe('100.0%')
    expect(formatPercent(undefined)).toBe('—')
    expect(formatPercent(Number.NaN)).toBe('—')
  })

  it('formats milliseconds and handles gaps', () => {
    expect(formatMillis(12.4)).toBe('12 мс')
    expect(formatMillis(undefined)).toBe('—')
  })

  it('passes through unparsable timestamps', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('2026-10-10T00:00:00+00:00')).toBeTypeOf('string')
  })
})
