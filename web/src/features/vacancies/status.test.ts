import { describe, expect, it } from 'vitest'
import { canWithdraw, employerActions, nextStatuses } from '@/features/vacancies/status'

describe('application status transitions', () => {
  it('mirrors the backend pipeline', () => {
    expect(nextStatuses('applied')).toEqual(['reviewing', 'invited', 'rejected'])
    expect(nextStatuses('reviewing')).toEqual(['invited', 'rejected'])
    expect(nextStatuses('invited')).toEqual(['hired', 'rejected'])
  })

  it('has no outgoing transitions for terminal statuses', () => {
    for (const terminal of ['rejected', 'hired', 'withdrawn'] as const) {
      expect(nextStatuses(terminal)).toEqual([])
      expect(employerActions(terminal)).toEqual([])
    }
  })

  it('lets a candidate withdraw only while the process is open', () => {
    expect(canWithdraw('applied')).toBe(true)
    expect(canWithdraw('reviewing')).toBe(true)
    expect(canWithdraw('invited')).toBe(true)
    expect(canWithdraw('rejected')).toBe(false)
    expect(canWithdraw('hired')).toBe(false)
    expect(canWithdraw('withdrawn')).toBe(false)
  })
})
