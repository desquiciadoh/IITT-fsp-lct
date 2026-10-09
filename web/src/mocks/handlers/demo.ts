import { http, HttpResponse } from 'msw'
import { me } from '@/mocks/fixtures/me'
import { setMockMe } from '@/mocks/handlers/core'

const stub = (data: unknown) =>
  HttpResponse.json(data as Record<string, unknown>, {
    headers: { 'X-Stub': 'true' },
  })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors },
    {
      status,
      headers: {
        'Content-Type': 'application/problem+json',
        'X-Stub': 'true',
      },
    },
  )

const PERSONA_ME: Record<string, typeof me.candidate> = {
  candidate_fsp: me.candidate,
  candidate_plain: me.candidatePlain,
  employer: me.employer,
}

/**
 * Only `POST /api/demo/reset` is a gap (G4) — persona login and time travel
 * exist on the backend, so `missing` mode must NOT intercept them: a mocked
 * response sets no session cookie and breaks `/api/me`.
 */
export const demoGapHandlers = [
  http.post('*/api/demo/reset', () => {
    setMockMe(me.candidate)
    return json({ ok: true })
  }),
]

/** Full demo suite for `all` mode (no backend). */
export const demoHandlers = [
  http.post('*/api/demo/persona', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { persona?: string }
    const id = body.persona ?? 'candidate_fsp'
    const next = PERSONA_ME[id]
    if (!next) {
      return problem(400, 'validation_failed', 'Unknown persona.', [
        { field: 'persona', msg: 'Unknown persona.' },
      ])
    }
    setMockMe(next)
    return json({
      id: next.id,
      role: next.role,
      email: next.email,
      email_verified: next.email_verified,
      demo: true,
      company_id: next.company_id ?? null,
      onboarding_step: next.onboarding_step,
    })
  }),
  http.post('*/api/demo/time-travel', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { days?: number }
    return json({ clock_offset_days: body.days ?? 30 })
  }),
]
