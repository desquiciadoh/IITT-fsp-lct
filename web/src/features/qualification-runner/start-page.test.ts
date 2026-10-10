import { describe, expect, it } from 'vitest'
import {
  TEST_RULES,
  assessmentKindFor,
  countdownTo,
  formatCountdown,
  resolveStartView,
} from './start-page'

/**
 * FE-05 start screen — pure logic tests (node env, no DOM).
 * The component itself is exercised end-to-end against the stateful MSW mock
 * (`VITE_API_MOCKS=all`); see docs/FE-05-Start-Screen.md.
 */

describe('countdownTo', () => {
  const now = Date.UTC(2026, 9, 10, 12, 0, 0) // fixed "now"

  it('splits remaining time into h/m/s (rounds up to whole seconds)', () => {
    const at = new Date(now + (2 * 3600 + 5 * 60 + 3) * 1000 + 400).toISOString()
    expect(countdownTo(at, now)).toEqual({ done: false, hours: 2, minutes: 5, seconds: 4 })
  })

  it('is done for missing / invalid / past timestamps', () => {
    expect(countdownTo(null, now)).toEqual({ done: true, hours: 0, minutes: 0, seconds: 0 })
    expect(countdownTo(undefined, now)).toMatchObject({ done: true })
    expect(countdownTo('not-a-date', now)).toMatchObject({ done: true })
    expect(countdownTo(new Date(now - 1000).toISOString(), now)).toMatchObject({ done: true })
  })

  it('formats with hours only when needed', () => {
    const in48h = new Date(now + 48 * 60 * 60 * 1000).toISOString()
    expect(formatCountdown(countdownTo(in48h, now))).toBe('48 ч 00 мин 00 с')
    expect(formatCountdown(countdownTo(new Date(now + 65_000).toISOString(), now))).toBe('01:05')
  })
})

describe('resolveStartView', () => {
  const base = { can_start: true, promotion_available: false }

  it('loading wins first', () => {
    expect(resolveStartView(undefined, true, false)).toBe('loading')
  })

  it('error on request failure and fail-closed on unknown block reason', () => {
    expect(resolveStartView(undefined, false, true)).toBe('error')
    expect(
      resolveStartView({ ...base, can_start: false, reason: 'something_else' }, false, false),
    ).toBe('error')
  })

  it('active session → resume takes priority over cooldown', () => {
    const e = {
      ...base,
      can_start: false,
      active_session_id: 'mock-as-1',
      reason: 'session_in_progress',
    }
    expect(resolveStartView(e, false, false)).toBe('resume')
  })

  it('cooldown_active → cooldown', () => {
    const e = { ...base, can_start: false, reason: 'cooldown_active', next_attempt_at: 'x' }
    expect(resolveStartView(e, false, false)).toBe('cooldown')
  })

  it('can_start → form', () => {
    expect(resolveStartView(base, false, false)).toBe('form')
  })
})

describe('assessmentKindFor', () => {
  it('starts a promotion session when eligibility allows it', () => {
    expect(assessmentKindFor({ can_start: true, promotion_available: true })).toBe('promotion')
  })

  it('defaults to an initial session otherwise', () => {
    expect(assessmentKindFor({ can_start: true, promotion_available: false })).toBe('initial')
    expect(assessmentKindFor(undefined)).toBe('initial')
  })
})

describe('TEST_RULES', () => {
  it('is shown on the start screen (FE2.md §FE-05 "read the rules")', () => {
    expect(TEST_RULES.length).toBeGreaterThanOrEqual(3)
    expect(TEST_RULES.every((r) => r.length > 0)).toBe(true)
  })
})
