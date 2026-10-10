import { describe, expect, it } from 'vitest'
import type { AssessmentItem } from '@/api/types'
import { buildAnswerInput, resultPath, skewAdjustedDeadline } from './test-runner-page'

/**
 * FE-05 runner — pure logic tests (node env, no DOM).
 * The component itself is exercised end-to-end against the stateful MSW mock
 * (`VITE_API_MOCKS=all`); see docs/FE-05-Test-Runner.md.
 */

const base = (over: Partial<AssessmentItem>): AssessmentItem =>
  ({
    item_id: 'q-1',
    seq: 1,
    stem_md: 'stem',
    code: null,
    options: null,
    input_type: 'choice',
    time_limit_s: 60,
    deadline_at: '2026-10-10T12:01:00.000Z',
    served_at: '2026-10-10T12:00:00.000Z',
    ...over,
  }) as AssessmentItem

describe('skewAdjustedDeadline', () => {
  const received = Date.UTC(2026, 9, 10, 9, 0, 30) // local clock "off" by 3 h

  it('keeps only the served→deadline duration, anchored to local receive time', () => {
    const out = skewAdjustedDeadline(base({}), received)
    expect(out).toBe(new Date(received + 60_000).toISOString())
  })

  it('a skewed device clock cannot lengthen or shorten the budget', () => {
    // Server and local absolute timestamps disagree; remaining time must not.
    const item = base({ served_at: new Date(Date.UTC(2026, 9, 10, 12, 0, 0)).toISOString() })
    const adjusted = Date.parse(skewAdjustedDeadline(item, received))
    expect(adjusted - received).toBe(60_000)
  })

  it('falls back to the raw deadline when timestamps are missing/unparseable', () => {
    expect(skewAdjustedDeadline(base({ served_at: '' as string }), received)).toBe(
      '2026-10-10T12:01:00.000Z',
    )
    expect(skewAdjustedDeadline(base({ deadline_at: 'garbage' }), received)).toBe('garbage')
    expect(skewAdjustedDeadline(base({}), 0)).toBe('2026-10-10T12:01:00.000Z')
  })

  it('clamps negative durations to zero elapsed', () => {
    const item = base({ deadline_at: '2026-10-10T11:59:00.000Z' }) // before served_at
    expect(skewAdjustedDeadline(item, received)).toBe(new Date(received).toISOString())
  })
})

describe('buildAnswerInput', () => {
  const integrity = { focus_loss: 2, paste: 1 }

  it('choice items send option_id', () => {
    expect(buildAnswerInput(base({}), 'b', 'ignored', integrity)).toEqual({
      item_id: 'q-1',
      option_id: 'b',
      integrity,
    })
  })

  it('empty choice auto-submit sends an empty option_id (counts as incorrect)', () => {
    expect(buildAnswerInput(base({}), null, '', integrity).option_id).toBe('')
  })

  it('number/text items send a trimmed value', () => {
    const num = base({ input_type: 'number' })
    expect(buildAnswerInput(num, null, '  42 ', integrity)).toEqual({
      item_id: 'q-1',
      value: '42',
      integrity,
    })
    const txt = base({ input_type: 'text' })
    expect(buildAnswerInput(txt, null, ' answer ', integrity).value).toBe('answer')
  })
})

describe('resultPath', () => {
  it('points at the FE-06 result route', () => {
    expect(resultPath('mock-as-1')).toBe('/candidate/qualification/mock-as-1/result')
  })
})
