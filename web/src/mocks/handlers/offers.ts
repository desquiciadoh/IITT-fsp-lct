import { http, HttpResponse } from 'msw'
import type { Offer } from '@/api/types'

/**
 * `all` mode (no backend): stateful offer store with the FE-07 contract —
 * optimistic-lock `version`, sent → viewed → accepted/declined transitions,
 * 409 `version_conflict` / `invalid_transition` as problem+json (R4).
 *
 * FE-11 adds the employer side: `X-FSP-View: employer` switches GET /api/offers
 * to a separate employer board store, POST /api/offers creates offers there
 * (422 salary_invalid / serializer errors, 403 candidate_not_reachable), and
 * withdraw is allowed in sent/viewed. Candidate identity on the employer
 * payload is mocked (`talent`) because the real API lacks it (gap G10).
 */

const json = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

const now = new Date().toISOString()
const in7d = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()

type MutableOffer = { -readonly [K in keyof Offer]: Offer[K] }

const store: MutableOffer[] = [
  {
    id: 'off-1',
    title: 'Senior Backend Engineer',
    description: 'Микросервисы на Python, высокая нагрузка, свои разработки.',
    company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
    position: 'Senior Backend',
    salary_min: 300000,
    salary_max: 420000,
    salary_type: 'gross',
    currency: 'RUB',
    contact_channel: 'platform',
    status: 'sent',
    why_you: [
      { kind: 'plus', text: 'Совпадение по Python и PostgreSQL', source: 'test' },
      { kind: 'plus', text: 'Подтверждённый грейд Middle', source: 'test' },
      { kind: 'info', text: 'Опыт в ФСП повышает рейтинг', source: 'fsp' },
    ],
    version: 1,
    expires_at: in7d,
    created_at: now,
    updated_at: now,
    candidate_contacts: null,
  },
  {
    id: 'off-2',
    title: 'Backend Developer (Middle)',
    description: 'Продуктовая команда, гибрид в Москве.',
    company: { id: 'comp-2', name: 'DataForge', trust_level: 'domain' },
    position: 'Backend Developer',
    salary_min: 220000,
    salary_max: 300000,
    salary_type: 'net',
    currency: 'RUB',
    contact_channel: 'email',
    status: 'viewed',
    why_you: [{ kind: 'plus', text: 'Зарплата выше твоего потолка', source: 'declared' }],
    version: 2,
    expires_at: in7d,
    created_at: now,
    updated_at: now,
    candidate_contacts: null,
  },
  {
    id: 'off-3',
    title: 'Team Lead Backend',
    description: 'Руководство направлением, удалёнка.',
    company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
    position: 'Team Lead',
    salary_min: 400000,
    salary_max: 520000,
    salary_type: 'gross',
    currency: 'RUB',
    contact_channel: 'telegram',
    contact_value: '@acme_jobs',
    status: 'accepted',
    why_you: [{ kind: 'plus', text: 'Лидерский опыт и менторство', source: 'test' }],
    version: 3,
    expires_at: null,
    created_at: now,
    updated_at: now,
    candidate_contacts: {
      full_name: 'Мария Иванова',
      email: 'maria@acme.example.com',
      phone: '+7 900 000-00-00',
      telegram: '@hr_acme',
    },
  },
]

const TRANSITIONS: Record<string, Record<string, Offer['status']>> = {
  view: { sent: 'viewed' },
  accept: { viewed: 'accepted' },
  decline: { viewed: 'declined' },
  // FE-11: the employer may withdraw while the offer is still open.
  withdraw: { sent: 'withdrawn', viewed: 'withdrawn' },
}

/**
 * FE-11 employer board store. `talent` imitates the candidate identity that the
 * real employer payload does not expose yet (gap G10) — the UI must fall back
 * to title/salary/status/dates when it is missing.
 */
type EmployerOffer = MutableOffer & { talent?: { public_id: string; display_name: string } | null }

const employerStore: EmployerOffer[] = [
  {
    id: 'off-e1',
    title: 'Senior Backend Engineer',
    description: 'Микросервисы на Python, высокая нагрузка.',
    position: 'Senior Backend',
    candidate_public_id: 'pub-anna',
    talent: { public_id: 'pub-anna', display_name: 'Анна Петрова' },
    salary_min: 320000,
    salary_max: 450000,
    salary_type: 'gross',
    currency: 'RUB',
    contact_channel: 'email',
    contact_value: 'hr@acme.example.com',
    status: 'sent',
    why_you: [],
    version: 1,
    expires_at: in7d,
    created_at: now,
    updated_at: now,
    candidate_contacts: null,
  },
  {
    id: 'off-e2',
    title: 'Backend Developer (Middle)',
    description: 'Продуктовая команда, гибрид в Москве.',
    position: 'Backend Developer',
    candidate_public_id: 'pub-maria',
    talent: { public_id: 'pub-maria', display_name: 'Мария Иванова' },
    salary_min: 220000,
    salary_max: 300000,
    salary_type: 'net',
    currency: 'RUB',
    contact_channel: 'telegram',
    contact_value: '@acme_hr',
    status: 'accepted',
    why_you: [],
    version: 3,
    expires_at: null,
    created_at: now,
    updated_at: now,
    // B16: contacts are exposed only while status === 'accepted'.
    candidate_contacts: {
      full_name: 'Мария Иванова',
      email: 'maria@example.com',
      phone: '+7 921 111-22-33',
      telegram: '@maria_dev',
    },
  },
]

let employerSeq = 3

export const offerHandlers = [
  http.get('*/api/offers', ({ request }) => {
    const url = new URL(request.url)
    const status = url.searchParams.get('status')
    const employerView = request.headers.get('X-FSP-View') === 'employer'
    const source: EmployerOffer[] = employerView ? employerStore : store
    const items = status && status !== 'all' ? source.filter((o) => o.status === status) : source
    return json(items)
  }),
  http.post('*/api/offers', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const str = (key: string) => (typeof body[key] === 'string' ? String(body[key]).trim() : '')
    const num = (key: string) => (typeof body[key] === 'number' ? (body[key] as number) : NaN)

    // Serializer-level required fields (DRF-style 422 field errors).
    const fieldErrors: Record<string, string[]> = {}
    if (!str('candidate_public_id')) fieldErrors.candidate_public_id = ['This field is required.']
    if (!str('title')) fieldErrors.title = ['This field is required.']
    if (!str('contact_channel')) fieldErrors.contact_channel = ['This field is required.']
    if (!['email', 'phone', 'telegram', 'platform'].includes(str('contact_channel'))) {
      fieldErrors.contact_channel = ['"value" is not a valid choice.']
    }
    if (Object.keys(fieldErrors).length > 0) {
      return HttpResponse.json(
        { type: 'about:blank', title: 'validation_failed', status: 422, code: 'validation_failed', errors: fieldErrors },
        { status: 422, headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' } },
      )
    }

    // Salary contract: positive bounds, min <= max, explicit gross/net (B15).
    const salaryMin = num('salary_min')
    const salaryMax = num('salary_max')
    if (!(salaryMin > 0) || !(salaryMax > 0) || salaryMin > salaryMax) {
      return problem(422, 'salary_invalid', 'Salary range is invalid: expected 0 < min <= max.')
    }

    // Reachability gate: reserved id demoing the 403 path (FE-11 error mapping).
    if (str('candidate_public_id') === 'pub-unreachable') {
      return problem(403, 'candidate_not_reachable', 'The candidate has not allowed direct contact yet.')
    }

    const days = typeof body.expires_in_days === 'number' ? body.expires_in_days : 14
    const offer: EmployerOffer = {
      id: `off-e${employerSeq++}`,
      title: str('title'),
      description: str('description'),
      position: str('position_id') || null,
      candidate_public_id: str('candidate_public_id'),
      // G10: mocked candidate identity on the employer payload.
      talent: { public_id: str('candidate_public_id'), display_name: `Кандидат ${str('candidate_public_id')}` },
      salary_min: salaryMin,
      salary_max: salaryMax,
      salary_type: (body.salary_type === 'net' ? 'net' : 'gross') as Offer['salary_type'],
      currency: str('currency') || 'RUB',
      contact_channel: str('contact_channel') as Offer['contact_channel'],
      contact_value: str('contact_value'),
      status: 'sent',
      why_you: [{ kind: 'info', text: 'Сервер рассчитает «почему ты» позже (B9)', source: 'test' }],
      version: 1,
      expires_at: new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      candidate_contacts: null,
    }
    employerStore.unshift(offer)
    return json(offer, 201)
  }),
  http.get('*/api/offers/:id', ({ params }) => {
    const offer = store.find((o) => o.id === params.id) ?? employerStore.find((o) => o.id === params.id)
    if (!offer) return problem(404, 'not_found', 'Offer not found.')
    return json(offer)
  }),
  http.post('*/api/offers/:id/:action', async ({ params, request }) => {
    // Candidate store first, then the FE-11 employer board (withdraw lives there).
    const offer =
      store.find((o) => o.id === params.id) ?? employerStore.find((o) => o.id === params.id)
    if (!offer) return problem(404, 'not_found', 'Offer not found.')
    const action = String(params.action)
    const allowed = TRANSITIONS[action]
    if (!allowed) return problem(404, 'not_found', 'Unknown action.')

    const body = (await request.json().catch(() => ({}))) as {
      version?: number
      reason?: string
      comment?: string
    }
    if (body.version !== offer.version) {
      return problem(409, 'version_conflict', 'The offer has changed, reload and retry.')
    }
    const next = allowed[offer.status]
    if (!next) {
      return problem(409, 'invalid_transition', `Cannot ${action} an offer in status ${offer.status}.`)
    }
    if (action === 'decline' && !body.reason) {
      return problem(400, 'validation_failed', 'A decline reason is required.')
    }

    offer.status = next
    offer.version += 1
    offer.updated_at = new Date().toISOString()
    if (action === 'decline') {
      offer.decline_reason = (body.reason as Offer['decline_reason']) ?? null
      offer.decline_comment = body.comment ?? null
    }
    if (action === 'accept' && !offer.candidate_contacts) {
      offer.candidate_contacts = {
        full_name: 'Мария Иванова',
        email: 'maria@acme.example.com',
        phone: '+7 900 000-00-00',
        telegram: '@hr_acme',
      }
    }
    return json(offer)
  }),
]
