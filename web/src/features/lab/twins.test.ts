import { describe, expect, it } from 'vitest'
import type { LabTwinItem } from '@/api/types'
import {
  difficultyRatio,
  formatDuration,
  meanB,
  twinDuration,
  twinMeanDifficulty,
  twinTopicCounts,
} from '@/features/lab/twins'

const twin = (topic: string, b: number, time = 60): LabTwinItem => ({
  family_id: `fam.${topic}`,
  topic,
  level: 'middle',
  b,
  time_limit_s: time,
  instance_a: { stem_md: 'a', input: 'choice', code: null, options: [] },
  instance_b: { stem_md: 'b', input: 'choice', code: null, options: [] },
})

describe('difficultyRatio', () => {
  it('maps the IRT range to 0..1 and clamps outliers', () => {
    expect(difficultyRatio(0)).toBe(0.5)
    expect(difficultyRatio(-3)).toBe(0)
    expect(difficultyRatio(3)).toBe(1)
    expect(difficultyRatio(-10)).toBe(0)
    expect(difficultyRatio(10)).toBe(1)
    expect(difficultyRatio(Number.NaN)).toBe(0)
  })
})

describe('meanB', () => {
  it('averages and guards the empty case', () => {
    expect(meanB([-1, 1])).toBe(0)
    expect(meanB([])).toBe(0)
  })
})

describe('twinMeanDifficulty / twinDuration', () => {
  it('computes over the slot list', () => {
    const twins = [twin('sql', -1, 60), twin('python', 1, 90)]
    expect(twinMeanDifficulty(twins)).toBe(0)
    expect(twinDuration(twins)).toBe(150)
  })

  it('handles undefined', () => {
    expect(twinMeanDifficulty(undefined)).toBe(0)
    expect(twinDuration(undefined)).toBe(0)
  })
})

describe('twinTopicCounts', () => {
  it('counts topics in first-seen order', () => {
    expect(twinTopicCounts([twin('sql', 0), twin('python', 0), twin('sql', 0)])).toEqual([
      { topic: 'sql', count: 2 },
      { topic: 'python', count: 1 },
    ])
  })
})

describe('formatDuration', () => {
  it('formats seconds, whole minutes and mixed', () => {
    expect(formatDuration(0)).toBe('0 с')
    expect(formatDuration(45)).toBe('45 с')
    expect(formatDuration(120)).toBe('2 мин')
    expect(formatDuration(95)).toBe('1 мин 35 с')
  })
})
