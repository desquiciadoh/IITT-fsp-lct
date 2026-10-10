import { http, HttpResponse } from 'msw'
import type { Offer } from '@/api/types'
import { me } from '@/mocks/fixtures/me'
import { POSITION_TITLES } from '@/mocks/handlers/employer'

/**
 * `all` mode (no backend): stateful offer store shared by both sides of the
 * flow — FE-07 (candidate inbox: view/accept/decline) and FE-11 (employer
 * board: POST /api/offers, withdraw, contacts after acceptance).
 * Optimistic-lock `version`, sent → viewed → accepted/declined transitions,
 * 409 `version_conflict` / `invalid_transition` and 422 `salary_invalid` /
 * 403 `candidate_not_reachable` as problem+json (R4).
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
      full_name: 'Анна ФСП',
      email: 'anna.fsp@example.com',
      phone: '+7 900 123-45-67',
      telegram: '@anna_fsp',
    },
  },
]

const TRANSITIONS: Record<string, Record<string, Offer['status']>> = {
  view: { sent: 'viewed' },
  accept: { viewed: 'accepted' },
  decline: { viewed: 'declined' },
  // FE-11: the employer may withdraw while the candidate has not decided yet.
  withdraw: { sent: 'withdrawn', viewed: 'withdrawn' },
}

/** Reachability mirrors the BE grant model (B16): public_id + open_to_offers. */
const CANDIDATES: Record<string, { open_to_offers: boolean; blocked_company_ids: string[] }> = {
  'pub-anna-1': { open_to_offers: true, blocked_company_ids: [] },
  'pub-alex-1': { open_to_offers: false, blocked_company_ids: [] },
}

// --- FE-11: create offer (POST /api/offers) ----------------------------------

type CreateOfferBody = {
  candidate_public_id?: unknown
  position_id?: unknown
  title?: unknown
  description?: unknown
  salary_min?: unknown
  salary_max?: unknown
  salary_type?: unknown
  contact_channel?: unknown
  contact_value?: unknown
  expires_in_days?: unknown
  why_you?: unknown
}

const CHANNELS = ['email', 'phone', 'telegram', 'platform'] as const

let offerSeq = 100

function buildOffer(body: CreateOfferBody): Offer {
  const salaryMin = Number(body.salary_min)
  const salaryMax = Number(body.salary_max)
  const errors: Record<string, string[]> = {}
  if (!Number.isFinite(salaryMin) || salaryMin <= 0) errors.salary_min = ['Введите зарплату больше нуля.']
  if (!Number.isFinite(salaryMax) || salaryMax <= 0) errors.salary_max = ['Введите зарплату больше нуля.']
  if (Number.isFinite(salaryMin) && Number.isFinite(salaryMax) && salaryMax < salaryMin) {
    errors.salary_max = ['Максимум не может быть меньше минимума.']
  }
  if (Object.keys(errors).length > 0) {
    throw { __problem: { status: 422, code: 'salary_invalid', detail: 'Salary range is invalid.', errors } }
  }

  const publicId = typeof body.candidate_public_id === 'string' ? body.candidate_public_id : ''
  const candidate = CANDIDATES[publicId]
  if (!candidate || !candidate.open_to_offers) {
    throw { __problem: { status: 403, code: 'candidate_not_reachable', detail: 'The candidate is not reachable for offers.' } }
  }
  if (candidate.blocked_company_ids.includes(me.employer.company_id ?? '')) {
    throw { __problem: { status: 403, code: 'candidate_not_reachable', detail: 'The candidate blocked this company.' } }
  }

  const title = typeof body.title === 'string' ? body.title.trim() : ''
  const channel = String(body.contact_channel ?? '')
  const contactValue = typeof body.contact_value === 'string' ? body.contact_value.trim() : ''
  const fieldErrors: Record<string, string[]> = {}
  if (!title) fieldErrors.title = ['Название обязательно.']
  if (!(CHANNELS as readonly string[]).includes(channel)) fieldErrors.contact_channel = ['Недопустимый канал связи.']
  if (!contactValue) fieldErrors.contact_value = ['Укажите контакт для связи.']
  if (Object.keys(fieldErrors).length > 0) {
    throw { __problem: { status: 400, code: 'validation_failed', detail: 'Validation failed.', errors: fieldErrors } }
  }

  const days = Number(body.expires_in_days ?? 7)
  const ts = new Date().toISOString()
  // G10: the employer payload has no candidate identity yet — resolve the
  // vacancy title from the mock position store for display purposes.
  const positionId = typeof body.position_id === 'string' ? body.position_id : ''
  const positionTitle = POSITION_TITLES[positionId] ?? null
  const offer: MutableOffer = {
    id: `off-new-${offerSeq++}`,
    title,
    description: typeof body.description === 'string' ? body.description : '',
    company: { id: me.employer.company_id ?? 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
    position: positionTitle,
    candidate_public_id: publicId,
    salary_min: salaryMin,
    salary_max: salaryMax,
    salary_type: body.salary_type === 'net' ? 'net' : 'gross',
    currency: 'RUB',
    contact_channel: channel as Offer['contact_channel'],
    contact_value: contactValue,
    status: 'sent',
    // B9: the server computes why_you — a client-sent value is ignored.
    why_you: [{ kind: 'info', text: 'Оффер отправлен работодателем', source: 'declared' }],
    version: 1,
    expires_at: Number.isFinite(days) && days > 0 ? new Date(Date.now() + days * 86_400_000).toISOString() : null,
    created_at: ts,
    updated_at: ts,
    candidate_contacts: null,
  }
  store.unshift(offer)
  return offer
}

export const offerHandlers = [
  http.get('*/api/offers', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status')
    const items = status && status !== 'all' ? store.filter((o) => o.status === status) : store
    return json(items)
  }),
  http.post('*/api/offers', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as CreateOfferBody
    try {
      return json(buildOffer(body), 201)
    } catch (e) {
      const p = (e as { __problem?: { status: number; code: string; detail: string; errors?: unknown } })?.__problem
      if (p) return problem(p.status, p.code, p.detail, p.errors)
      throw e
    }
  }),
  http.get('*/api/offers/:id', ({ params }) => {
    const offer = store.find((o) => o.id === params.id)
    if (!offer) return problem(404, 'not_found', 'Offer not found.')
    return json(offer)
  }),
  http.post('*/api/offers/:id/:action', async ({ params, request }) => {
    const offer = store.find((o) => o.id === params.id)
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
      // B16: contacts are granted on acceptance — the employer side (FE-11)
      // reads them from the same store, so both views stay consistent.
      offer.candidate_contacts = {
        full_name: 'Анна ФСП',
        email: 'anna.fsp@example.com',
        phone: '+7 900 123-45-67',
        telegram: '@anna_fsp',
      }
    }
    return json(offer)
  }),
]
