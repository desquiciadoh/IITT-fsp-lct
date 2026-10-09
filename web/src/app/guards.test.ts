import { describe, expect, it } from 'vitest'
import { onboardingRedirect } from '@/app/guards'
import type { Me } from '@/api/types'

function me(step: Me['onboarding_step'], role: Me['role'] = 'candidate'): Me {
  return {
    id: 'u1',
    role,
    email: 'x@example.com',
    email_verified: true,
    demo: true,
    onboarding_step: step,
  }
}

describe('onboardingRedirect', () => {
  it('lets the runner through while the step is qualification', () => {
    expect(onboardingRedirect(me('qualification'), '/candidate/qualification/abc')).toBeNull()
  })

  it('lets the result page through while the step is qualification', () => {
    expect(onboardingRedirect(me('qualification'), '/candidate/qualification/abc/result')).toBeNull()
  })

  it('sends a candidate in qualification to the start screen', () => {
    expect(onboardingRedirect(me('qualification'), '/candidate')).toBe(
      '/candidate/qualification/start',
    )
  })

  it('sends a consent-stage candidate to the matching onboarding step', () => {
    expect(onboardingRedirect(me('consent'), '/candidate/offers')).toBe(
      '/candidate/onboarding/consent',
    )
  })

  it('passes a finished candidate through', () => {
    expect(onboardingRedirect(me('done'), '/candidate')).toBeNull()
  })

  it('never redirects employers or anonymous users', () => {
    expect(onboardingRedirect(me('consent', 'employer'), '/employer')).toBeNull()
    expect(onboardingRedirect(null, '/candidate')).toBeNull()
  })
})
