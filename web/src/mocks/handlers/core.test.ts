import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { coreHandlers, completeCandidateQualification, setMockMe } from '@/mocks/handlers/core'
import { me } from '@/mocks/fixtures/me'

/**
 * R22 — in `all` mode neither saving the profile nor claiming a grade may
 * complete onboarding: the backend keeps `qualification` until a test finishes
 * (`apps/identity/views.py:151`). Only the mocked assessment finish advances
 * to `done`.
 */
const server = setupServer(...coreHandlers)

const getStep = async (): Promise<string | undefined> => {
  const res = await fetch('http://localhost/api/me')
  const body = (await res.json()) as { onboarding_step?: string }
  return body.onboarding_step
}

const putProfile = (body: Record<string, unknown>) =>
  fetch('http://localhost/api/candidates/me', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('core mock · onboarding gate (R22)', () => {
  it('claiming a grade keeps onboarding at qualification', async () => {
    setMockMe({ ...me.candidate, onboarding_step: 'profile' })

    const res = await putProfile({ claimed_grade: 'middle' })
    expect(res.ok).toBe(true)

    expect(await getStep()).toBe('qualification')
  })

  it('saving the profile advances to qualification, never done', async () => {
    setMockMe({ ...me.candidate, onboarding_step: 'profile' })

    const res = await putProfile({ full_name: 'Анна' })
    expect(res.ok).toBe(true)

    expect(await getStep()).toBe('qualification')
  })

  it('finishing the assessment moves onboarding to done', async () => {
    setMockMe({ ...me.candidate, onboarding_step: 'qualification' })
    completeCandidateQualification()
    expect(await getStep()).toBe('done')
  })
})
