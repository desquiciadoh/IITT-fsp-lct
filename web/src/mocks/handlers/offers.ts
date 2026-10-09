import { http, HttpResponse } from 'msw'
import type { Offer } from '@/api/types'

/**
 * `all` mode (no backend): stateful offer store with the FE-07 contract —
 * optimistic-lock `version`, sent → viewed → accepted/declined transitions,
 * 409 `version_conflict` / `invalid_transition` as problem+json (R4).
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
}

export const offerHandlers = [
  http.post('*/api/offers', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      candidate_public_id?: string
      title?: string
      description?: string
      salary_min?: number
      salary_max?: number
      salary_type?: string
      contact_channel?: string
      contact_value?: string
      expires_in_days?: number
    }
    if (
      !body.candidate_public_id ||
      !body.title?.trim() ||
      typeof body.salary_min !== 'number' ||
      typeof body.salary_max !== 'number' ||
      typeof body.salary_min !== 'number'
    ) {
      return problem(400, 'validation_failed', 'A candidate, title and salary range are required.')
    }
    const offer: MutableOffer = {
      id: `off-${store.length + 1}`,
      title: body.title.trim(),
      description: body.description ?? '',
      company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
      position: body.title.trim(),
      salary_min: Number(body.salary_min),
      salary_max: Number(body.salary_max),
      salary_type: (body.salary_type as Offer['salary_type']) ?? 'gross',
      currency: 'RUB',
      contact_channel: (body.contact_channel as Offer['contact_channel']) ?? 'platform',
      contact_value: body.contact_value ?? undefined,
      status: 'sent',
      why_you: [
        {
          kind: 'plus',
          text: 'Выполнена микрозадача — навык подтверждён компанией',
          source: 'microtask',
        },
      ],
      version: 1,
      expires_at: new Date(
        Date.now() + (body.expires_in_days ?? 7) * 24 * 60 * 60 * 1000,
      ).toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      candidate_contacts: null,
    }
    store.push(offer)
    return json(offer, 201)
  }),
  http.get('*/api/offers', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status')
    const items = status && status !== 'all' ? store.filter((o) => o.status === status) : store
    return json(items)
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
