import { http, HttpResponse } from 'msw'
import { me } from '@/mocks/fixtures/me'
import type { CandidateProfile, Me } from '@/api/types'

const stub = (init: ResponseInit = {}) =>
  new Headers({ 'X-Stub': 'true', ...(init.headers ?? {}) })

const json = (data: unknown, init: ResponseInit = {}) =>
  HttpResponse.json(data as Record<string, unknown>, { ...init, headers: stub(init) })

const problem = (
  status: number,
  code: string,
  detail: string,
  errors?: unknown,
) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors },
    {
      status,
      headers: stub({
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    },
  )

let currentMe = me.candidate
const registeredEmails = new Set<string>(['taken@example.com'])

const richProfile: CandidateProfile = {
  public_id: 'pub-anna-1',
  full_name: 'Анна ФСП',
  city: 'Москва',
  timezone: 'Europe/Moscow',
  specialization: 'backend',
  claimed_grade: 'middle',
  years_experience: '5',
  roles: ['разработчик', 'тимлид'],
  work_formats: ['hybrid', 'remote'],
  salary_min: 250000,
  salary_max: 350000,
  salary_type: 'gross',
  salary_floor: 220000,
  open_to_offers: true,
  blind_mode: false,
  blocked_company_ids: [],
  about: 'Пять лет разрабатываю бэкенд-сервисы на Python, вожу команду из трёх человек.',
  experience_text: '',
  completeness: 100,
  contacts: { email: 'anna.fsp@example.com', phone: '', telegram: '' },
  skills: [
    { id: 's1', name: 'Python', source: 'test' },
    { id: 's2', name: 'Django', source: 'fsp' },
    { id: 's3', name: 'PostgreSQL', source: 'declared' },
  ],
  league: {
    specialization: 'backend',
    grade: 'middle',
    status: 'confirmed',
    rating: 1842,
    percentile: 87,
    strength: 75,
  },
  fsp: {
    participant_id: 'fsp-777',
    sports_rank: 'ms',
    sync_status: 'ok',
    results: [
      {
        event_id: 'ev-1',
        event_name: 'Кубок СПб 2025',
        discipline: 'algorithms',
        date: '2025-05-17',
        placement: 2,
        tier: 'prize_winner',
        participants_total: 214,
      },
    ],
  },
  consents: { processing: true, publication: true, fsp_sync: true },
}

const emptyProfile: CandidateProfile = {
  public_id: 'pub-alex-1',
  full_name: '',
  city: '',
  timezone: '',
  specialization: '',
  claimed_grade: '',
  years_experience: null,
  roles: [],
  work_formats: [],
  salary_min: null,
  salary_max: null,
  salary_type: '',
  salary_floor: null,
  open_to_offers: true,
  blind_mode: false,
  blocked_company_ids: [],
  about: '',
  experience_text: '',
  completeness: 0,
  contacts: { email: 'alex.dev@example.com', phone: '', telegram: '' },
  skills: [],
  league: null,
  fsp: null,
  consents: null,
}

const profileStore = new Map<string, CandidateProfile>([
  [me.candidate.id, structuredClone(richProfile)],
  [me.candidatePlain.id, structuredClone(emptyProfile)],
])

function currentProfile(): CandidateProfile {
  let profile = profileStore.get(currentMe.id)
  if (!profile) {
    profile = structuredClone(emptyProfile)
    profileStore.set(currentMe.id, profile)
  }
  return profile
}

/** Demo persona login switches the mocked /api/me (see handlers/demo.ts). */
export function setMockMe(next: typeof me.candidate): void {
  currentMe = next
}

/**
 * `all` mode: mirror the backend's onboarding_step advance so the wizard →
 * gate flow works without a real backend — consent saved → profile,
 * profile/claim saved → qualification. The backend keeps `qualification`
 * until a test finishes (R22), so `done` is set by the mocked finish handler,
 * not here.
 */
function advanceStep(
  apply: (step: Me['onboarding_step']) => Me['onboarding_step'] | undefined,
): void {
  if (currentMe.role !== 'candidate') return
  const next = apply(currentMe.onboarding_step)
  if (next) currentMe = { ...currentMe, onboarding_step: next }
}

/** `all` mode: a finished test closes the qualification step (R22). */
export function completeQualification(): void {
  advanceStep((step) => (step === 'qualification' ? 'done' : undefined))
}

export const coreHandlers = [
  http.get('*/api/me', () => json(currentMe)),
  http.post('*/api/auth/register', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      email?: string
      password?: string
      role?: string
    }
    const errors: { field: string; msg: string }[] = []
    if (!body.email?.includes('@')) errors.push({ field: 'email', msg: 'Enter a valid email address.' })
    if ((body.password ?? '').length < 6) errors.push({ field: 'password', msg: 'Min length is 6 characters.' })
    if (body.role !== 'candidate' && body.role !== 'employer') {
      errors.push({ field: 'role', msg: 'Choose a role.' })
    }
    if (errors.length > 0) {
      return problem(400, 'validation_failed', 'Validation failed.', errors)
    }
    if (registeredEmails.has(body.email!)) {
      return problem(409, 'email_taken', 'This email is already registered.', [
        { field: 'email', msg: 'This email is already registered.' },
      ])
    }
    registeredEmails.add(body.email!)
    return json(
      {
        user_id: crypto.randomUUID(),
        email: body.email,
        role: body.role,
        email_verified: true,
      },
      { status: 201 },
    )
  }),
  http.post('*/api/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      email?: string
      password?: string
    }
    if (!body.email?.includes('@')) {
      return problem(400, 'validation_failed', 'Enter a valid email address.', [
        { field: 'email', msg: 'Enter a valid email address.' },
      ])
    }
    if (body.password === 'wrong') {
      return problem(401, 'bad_credentials', 'Invalid email or password.')
    }
    currentMe = body.email.startsWith('hr@') ? me.employer : me.candidate
    return json({
      id: currentMe.id,
      role: currentMe.role,
      email: currentMe.email,
      email_verified: currentMe.email_verified,
      demo: currentMe.demo,
      company_id: currentMe.company_id ?? null,
    })
  }),
  http.post('*/api/auth/logout', () =>
    new HttpResponse(null, { status: 204, headers: stub() }),
  ),
  http.get('*/api/auth/csrf', () => json({ detail: 'ok' })),
  http.get('*/api/candidates/me', () => json(currentProfile())),
  http.put('*/api/candidates/me', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const profile = currentProfile()
    const next = { ...profile, ...body } as CandidateProfile
    profileStore.set(currentMe.id, next)
    advanceStep((step) => {
      if (body.claimed_grade) return step === 'consent' ? 'profile' : 'qualification'
      if (step === 'profile') return 'qualification'
      return undefined
    })
    return json(next)
  }),
  http.put('*/api/candidates/me/consents', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const profile = currentProfile()
    profile.consents = {
      processing: Boolean(body.processing),
      publication: Boolean(body.publication),
      fsp_sync: Boolean(body.fsp_sync),
    }
    profileStore.set(currentMe.id, profile)
    advanceStep((step) => (step === 'consent' ? 'profile' : undefined))
    return json(profile.consents)
  }),
  http.post('*/api/candidates/me/resume', () =>
    json(
      {
        prefill: {
          specialization: 'backend',
          claimed_grade: 'middle',
          skills: ['Python', 'Django', 'PostgreSQL', 'k8s'],
          about:
            'Пять лет разрабатываю бэкенд-сервисы на Python, вожу команду из трёх человек.',
        },
        unknown_terms: ['k8s'],
        source: 'rules',
      },
    ),
  ),
]
