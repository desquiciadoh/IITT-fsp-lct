import { http, HttpResponse } from 'msw'
import type { ContactChannel, Offer } from '@/api/types'
import { grantContacts } from '@/mocks/handlers/scouting'

/**
 * `all` mode (no backend): stateful offer store with the FE-07 contract —
 * optimistic-lock `version`, sent → viewed → accepted/declined transitions,
 * 409 `version_conflict` / `invalid_transition` as problem+json (R4) — plus
 * the FE-11 employer side:
 *   POST /api/offers            → 201 (validations: 422 salary_invalid,
 *                                 403 candidate_not_reachable, 404 not_found);
 *   POST /api/offers/{id}/withdraw → version-locked, only sent/viewed;
 *   accept grants candidate contacts (cross-link seam into the scouting
 *   mock, so "send → accept → contacts on the board" works end-to-end).
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
  // FE-11: an employer sends to a pool candidate who may still be `sent`
  // (nobody has opened it yet) — accept from both states.
  accept: { sent: 'accepted', viewed: 'accepted' },
  decline: { viewed: 'declined' },
  withdraw: { sent: 'withdrawn', viewed: 'withdrawn' },
}

// --- FE-11 employer-side state -------------------------------------------------

/** Mutable per-offer extras that are not part of the public Offer shape. */
type OfferMeta = { candidate_public_id?: string; position_id?: string }
const meta = new Map<string, OfferMeta>()

/** Candidates hidden from scouting in the mock pool (private profile). */
const hiddenCandidates = new Set(['t-hidden'])

let seq = 0

const resetStore = () => {
  store.length = 3
  meta.clear()
  for (const o of store) {
    o.status = o.id === 'off-3' ? 'accepted' : o.id === 'off-2' ? 'viewed' : 'sent'
    o.version = o.id === 'off-3' ? 3 : o.id === 'off-2' ? 2 : 1
  }
  meta.set('off-1', { candidate_public_id: 't-001', position_id: 'pos-1' })
  meta.set('off-2', { candidate_public_id: 't-002', position_id: 'pos-1' })
  meta.set('off-3', { candidate_public_id: 't-003', position_id: 'pos-1' })
}

/** Test helper: reseed the store so wire tests are order-independent. */
export function __resetOffers() {
  resetStore()
}

resetStore()

export const offerHandlers = [
  http.post('*/api/_mock/offers/reset', () => {
    resetStore()
    return json({ ok: true })
  }),
  // FE-11 · employer sends an offer to a pool candidate. Contract rules:
  // salary_type is required (B15), why_you is server-computed (B9) and is
  // never accepted from the client.
  http.post('*/api/offers', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const str = (key: string) => (typeof body[key] === 'string' ? (body[key] as string).trim() : '')
    const num = (key: string) => (typeof body[key] === 'number' && Number.isFinite(body[key] as number) ? (body[key] as number) : NaN)

    const candidatePublicId = str('candidate_public_id')
    const positionId = str('position_id')
    if (!candidatePublicId || !positionId) {
      return problem(404, 'not_found', 'Candidate or position not found.')
    }
    if (hiddenCandidates.has(candidatePublicId)) {
      return problem(403, 'candidate_not_reachable', 'The candidate is hidden from scouting.')
    }

    const min = num('salary_min')
    const max = num('salary_max')
    const type = str('salary_type')
    if (!(min >= 0) || !(max > min) || !['gross', 'net'].includes(type)) {
      return problem(422, 'salary_invalid', 'Check the salary range: min ≥ 0, max > min, gross/net required.')
    }

    const channel = str('contact_channel')
    if (!['email', 'phone', 'telegram', 'platform'].includes(channel)) {
      return problem(422, 'validation_failed', 'Unknown contact channel.')
    }
    const contactValue = str('contact_value')
    if (channel !== 'platform' && !contactValue) {
      return problem(422, 'validation_failed', 'contact_value is required for email/phone/telegram.')
    }

    const days = num('expires_in_days')
    const nowIso = new Date().toISOString()
    seq += 1
    const id = `off-new-${seq}`
    const offer: MutableOffer = {
      id,
      title: str('title') || 'Оффер',
      description: str('description'),
      company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
      position: str('title') || undefined,
      candidate_public_id: candidatePublicId,
      salary_min: min,
      salary_max: max,
      salary_type: type as Offer['salary_type'],
      currency: 'RUB',
      contact_channel: channel as ContactChannel,
      contact_value: contactValue,
      status: 'sent',
      // B9: the server computes why_you — the client never sends it.
      why_you: [{ kind: 'plus', text: 'Совпадение по обязательным навыкам', source: 'test' }],
      version: 1,
      expires_at: days >= 1 ? new Date(Date.now() + Math.trunc(days) * 86_400_000).toISOString() : in7d,
      created_at: nowIso,
      updated_at: nowIso,
      candidate_contacts: null,
    }
    meta.set(id, { candidate_public_id: candidatePublicId, position_id: positionId })
    store.unshift(offer)
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
      // FE-11 cross-link: the scouting talent mock starts returning the
      // candidate's contacts to the company (grant), so the drawer/board
      // "contacts only after acceptance" scenario works end-to-end.
      const publicId = meta.get(offer.id)?.candidate_public_id
      if (publicId) grantContacts(publicId)
    }
    return json(offer)
  }),
]
