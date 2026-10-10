import { describe, expect, it } from 'vitest'
import { resetQualificationMock, setMockNow, isLate } from '@/mocks/handlers/qualification'

describe('dbg', () => {
  it('late', () => {
    resetQualificationMock()
    const servedAt = new Date(Date.UTC(2026, 9, 10, 12, 0, 0)).toISOString()
    const s = {
      id: 'x', specialization: 'backend', claimed_grade: 'middle', kind: 'initial', mode: 'full',
      status: 'in_progress', startedAt: servedAt, finishedAt: null, cursor: 0,
      servedAt, deadlineAt: new Date(Date.parse(servedAt) + 63_000).toISOString(), answers: [],
    } as never
    setMockNow(() => new Date(Date.parse(servedAt) + 61_000))
    console.log('isLate', isLate(s))
    expect(true).toBe(true)
  })
})
