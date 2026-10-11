/**
 * FE-11 · Send Offer & offers board — tests.
 *
 * Pure logic (schemas.ts):
 *   - toSendOfferInput: coercion, trimming, platform-channel contact reset,
 *     optional expiry;
 *   - offerFormSchema: salary range, salary_type required (B15), per-channel
 *     contact validation, why_you is not part of the form at all (B9).
 *
 * Wire contract (stateful MSW mock, node env, same handler objects as
 * mocks/server.ts):
 *   - POST /api/offers → 201 with server-computed why_you and status `sent`;
 *   - 422 salary_invalid, 403 candidate_not_reachable, 404 not_found;
 *   - POST /api/offers/{id}/withdraw — version-lock (409 version_conflict),
 *     state machine (409 invalid_transition after accept);
 *   - accept → contacts on the offer AND granted in the scouting talent mock
 *     (end-to-end "send → accept → contacts" acceptance scenario).
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { offerHandlers } from './offers'
import { scoutingHandlers } from './scouting'
import { offerFormSchema, toSendOfferInput, type OfferFormInput } from '@/features/employer/schemas'

const BASE = 'http://localhost'
const server = setupServer(...offerHandlers, ...scoutingHandlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(async () => {
  await fetch(`${BASE}/api/_mock/offers/reset`, { method: 'POST' })
})
afterAll(() => server.close())

async function req<T = unknown>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  return { status: res.status, body: (await res.json()) as T }
}

const post = <T = unknown>(path: string, body: unknown) => req<T>(path, { method: 'POST', body: JSON.stringify(body) })

// --- pure logic ----------------------------------------------------------------

const baseForm: OfferFormInput = {
  title: '  Backend Developer ',
  description: '  Product team ',
  salary_min: '200000',
  salary_max: '300000',
  salary_type: 'net',
  contact_channel: 'platform',
  contact_value: '',
}

describe('toSendOfferInput (FE-11)', () => {
  it('coerces numbers, trims strings, keeps salary_type explicit (B15)', () => {
    const out = toSendOfferInput({ ...baseForm, title: ' Lead ', salary_type: 'gross' })
    expect(out).toMatchObject({
      title: 'Lead',
      description: 'Product team',
      salary_min: 200000,
      salary_max: 300000,
      salary_type: 'gross',
      contact_channel: 'platform',
    })
    // `why_you` must never leak into the payload (server computes it, B9).
    expect(out).not.toHaveProperty('why_you')
  })

  it('drops contact_value for the platform channel, keeps it otherwise', () => {
    expect(toSendOfferInput({ ...baseForm, contact_channel: 'platform', contact_value: '  junk  ' }).contact_value).toBe('')
    expect(toSendOfferInput({ ...baseForm, contact_channel: 'email', contact_value: ' a@b.co ' }).contact_value).toBe('a@b.co')
  })

  it('expires_in_days is omitted when empty, forwarded when numeric', () => {
    expect(toSendOfferInput({ ...baseForm, expires_in_days: '' })).not.toHaveProperty('expires_in_days')
    expect(toSendOfferInput({ ...baseForm, expires_in_days: '21' })).toMatchObject({ expires_in_days: 21 })
  })
})

describe('offerFormSchema (FE-11)', () => {
  it('accepts a valid form and coerces salary to numbers', () => {
    const parsed = offerFormSchema.safeParse(baseForm)
    expect(parsed.success).toBe(true)
    if (parsed.success) expect(parsed.data.salary_max).toBe(300000)
  })

  it('rejects max < min with a field error on salary_max', () => {
    const parsed = offerFormSchema.safeParse({ ...baseForm, salary_min: '300000', salary_max: '200000' })
    expect(parsed.success).toBe(false)
    const issues = parsed.error?.issues ?? []
    expect(issues.some((i) => i.path.join('.') === 'salary_max')).toBe(true)
  })

  it('requires salary_type — an empty value fails (B15 gross-default trap)', () => {
    const parsed = offerFormSchema.safeParse({ ...baseForm, salary_type: '' })
    expect(parsed.success).toBe(false)
  })

  it('requires a contact for email/phone/telegram but not for platform', () => {
    expect(offerFormSchema.safeParse({ ...baseForm, contact_channel: 'email', contact_value: '' }).success).toBe(false)
    expect(offerFormSchema.safeParse({ ...baseForm, contact_channel: 'email', contact_value: 'not-an-email' }).success).toBe(false)
    expect(offerFormSchema.safeParse({ ...baseForm, contact_channel: 'platform', contact_value: '' }).success).toBe(true)
  })
})

// --- wire contract -------------------------------------------------------------

type OfferWire = {
  id: string
  status: string
  version: number
  why_you?: { kind: string; text: string }[]
  candidate_contacts?: { full_name?: string } | null
  expires_at?: string | null
}
type ProblemWire = { code?: string; detail?: string }

const validSend = {
  candidate_public_id: 't-001',
  position_id: 'pos-1',
  title: 'Senior Backend',
  description: 'Highload services',
  salary_min: 300000,
  salary_max: 400000,
  salary_type: 'net',
  contact_channel: 'telegram',
  contact_value: '@hr',
  expires_in_days: 10,
}

describe('POST /api/offers (employer side)', () => {
  it('201: stateful creation, server-computed why_you, status sent (B9)', async () => {
    const { status, body } = await post<OfferWire>('/api/offers', { ...validSend, why_you: 'should be ignored' })
    expect(status).toBe(201)
    expect(body.status).toBe('sent')
    expect(body.version).toBe(1)
    expect(Array.isArray(body.why_you)).toBe(true)
    expect(body.why_you!.length).toBeGreaterThan(0)
    expect(body.expires_at).toBeTruthy()

    // The new offer appears in the board list (GET /api/offers).
    const list = await req<OfferWire[]>('/api/offers')
    expect(list.body.some((o) => o.id === body.id)).toBe(true)
  })

  it('422 salary_invalid: max <= min or missing salary_type (B15)', async () => {
    const bad1 = await post<ProblemWire>('/api/offers', { ...validSend, salary_max: 100000 })
    expect(bad1.status).toBe(422)
    expect(bad1.body.code).toBe('salary_invalid')

    const bad2 = await post<ProblemWire>('/api/offers', { ...validSend, salary_type: undefined })
    expect(bad2.status).toBe(422)
    expect(bad2.body.code).toBe('salary_invalid')
  })

  it('403 candidate_not_reachable for hidden candidates', async () => {
    const r = await post<ProblemWire>('/api/offers', { ...validSend, candidate_public_id: 't-hidden' })
    expect(r.status).toBe(403)
    expect(r.body.code).toBe('candidate_not_reachable')
  })

  it('404 when candidate/position ids are missing', async () => {
    const r = await post<ProblemWire>('/api/offers', { ...validSend, candidate_public_id: '' })
    expect(r.status).toBe(404)
    expect(r.body.code).toBe('not_found')
  })
})

describe('POST /api/offers/{id}/withdraw (version-lock)', () => {
  it('200 with matching version → status withdrawn', async () => {
    const created = await post<OfferWire>('/api/offers', validSend)
    const r = await post<OfferWire>(`/api/offers/${created.body.id}/withdraw`, { version: 1 })
    expect(r.status).toBe(200)
    expect(r.body.status).toBe('withdrawn')
    expect(r.body.version).toBe(2)
  })

  it('409 version_conflict with a stale version → caller refetches', async () => {
    const r = await post<ProblemWire>('/api/offers/off-1/withdraw', { version: 99 })
    expect(r.status).toBe(409)
    expect(r.body.code).toBe('version_conflict')
    // After the conflict the board still serves fresh data (refetch path).
    const fresh = await req<OfferWire[]>('/api/offers?status=sent')
    expect(fresh.status).toBe(200)
  })

  it('409 invalid_transition once the offer is accepted', async () => {
    const accepted = await post<OfferWire>('/api/offers/off-1/view', { version: 1 })
    expect(accepted.status).toBe(200)
    const acc = await post<OfferWire>('/api/offers/off-1/accept', { version: 2 })
    expect(acc.body.status).toBe('accepted')
    const w = await post<ProblemWire>('/api/offers/off-1/withdraw', { version: 3 })
    expect(w.status).toBe(409)
    expect(w.body.code).toBe('invalid_transition')
  })
})

describe('accept → contacts (B16 end-to-end)', () => {
  it('contacts appear on the offer and unlock in the scouting talent card', async () => {
    const created = await post<OfferWire>('/api/offers', { ...validSend, candidate_public_id: 't-004' })
    await post(`/api/offers/${created.body.id}/view`, { version: 1 })
    const acc = await post<OfferWire>(`/api/offers/${created.body.id}/accept`, { version: 2 })
    expect(acc.status).toBe(200)
    expect(acc.body.status).toBe('accepted')
    expect(acc.body.candidate_contacts?.full_name).toBeTruthy()

    // Cross-link seam: GET /api/talent/{id} now returns granted contacts.
    const talent = await req<{ contacts: { full_name?: string } | null }>('/api/talent/t-004')
    expect(talent.status).toBe(200)
    expect(talent.body.contacts).not.toBeNull()
    expect(talent.body.contacts!.full_name).toBeTruthy()
  })

  it('before acceptance the talent card hides contacts', async () => {
    const talent = await req<{ contacts: unknown }>('/api/talent/t-005')
    expect(talent.body.contacts).toBeNull()
  })
})
