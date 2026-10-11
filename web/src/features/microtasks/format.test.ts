import { describe, expect, it } from 'vitest'
import {
  answerPreview,
  deadlinePassed,
  dropStage,
  scoreText,
} from '@/features/microtasks/format'
import type { MicroTaskDropCandidate } from '@/api/types'

function drop(overrides: Partial<MicroTaskDropCandidate>): MicroTaskDropCandidate {
  return {
    id: 'd1',
    task: {
      id: 't1',
      company: { id: 'c1', name: 'Acme' },
      title: 'Task',
      specialization: 'backend',
      grades: ['middle'],
      format: 'open',
      prompt_md: 'Solve it',
    },
    ...overrides,
  }
}

describe('dropStage', () => {
  it('walks pending → review → rated', () => {
    expect(dropStage(drop({}))).toBe('pending')
    expect(dropStage(drop({ submitted_at: '2026-10-01T10:00:00Z' }))).toBe('review')
    expect(
      dropStage(drop({ submitted_at: '2026-10-01T10:00:00Z', employer_rating: 4 })),
    ).toBe('rated')
  })
})

describe('scoreText', () => {
  it('formats auto-grade 0/1 and hides unknown scores', () => {
    expect(scoreText(1)).toBe('верно')
    expect(scoreText(0.75)).toBe('частично')
    expect(scoreText(0)).toBe('неверно')
    expect(scoreText(null)).toBe('—')
  })
})

describe('deadlinePassed', () => {
  it('treats missing deadlines as open', () => {
    expect(deadlinePassed(null)).toBe(false)
    expect(deadlinePassed(undefined)).toBe(false)
  })
  it('compares against now', () => {
    expect(deadlinePassed('2000-01-01T00:00:00Z')).toBe(true)
    expect(deadlinePassed('2999-01-01T00:00:00Z')).toBe(false)
  })
})

describe('answerPreview', () => {
  it('renders objects and truncates long text', () => {
    expect(answerPreview({ plan: 'a' })).toBe('{"plan":"a"}')
    expect(answerPreview('x'.repeat(200))).toHaveLength(121)
    expect(answerPreview('')).toBe('без ответа')
  })
})