/**
 * FE-11 pure-logic tests (node env): send-offer schema, error mapping,
 * payload building and board grouping rules.
 */
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import type { Offer } from '@/api/types'
import {
  OFFER_ERROR_MESSAGES,
  buildInitialForm,
  mapSendOfferError,
  prefillFromPosition,
  sendOfferSchema,
  toCreateOfferPayload,
} from './send-offer-schema'
import { canWithdraw, contactsVisible, groupByStatus } from './offers-board-page'

const validForm = {
  title: 'Senior Backend Engineer',
  description: 'Микросервисы, Python, высокая нагрузка',
  salaryMin: 300000,
  salaryMax: 420000,
  salaryType: 'gross' as const,
  contactChannel: 'email' as const,
  contactValue: 'hr@acme.ru',
  expiresInDays: 14,
}

describe('sendOfferSchema (FE-11)', () => {
  it('accepts a valid form', () => {
    expect(sendOfferSchema.safeParse(validForm).success).toBe(true)
  })

  it('rejects min > max with a Russian message on salaryMin', () => {
    const res = sendOfferSchema.safeParse({ ...validForm, salaryMin: 500000 })
    expect(res.success).toBe(false)
    if (!res.success) {
      const issue = res.error.issues.find((i) => i.path[0] === 'salaryMin')
      expect(issue?.message).toBe('Минимум не может быть больше максимума')
    }
  })

  it('requires an explicit salary_type — never relies on the backend default (B15)', () => {
    const res = sendOfferSchema.safeParse({ ...validForm, salaryType: '' })
    expect(res.success).toBe(false)
    if (!res.success) {
      expect(res.error.issues.some((i) => i.path[0] === 'salaryType')).toBe(true)
    }
  })

  it('rejects non-positive salaries', () => {
    expect(sendOfferSchema.safeParse({ ...validForm, salaryMin: 0 }).success).toBe(false)
    expect(sendOfferSchema.safeParse({ ...validForm, salaryMax: -1 }).success).toBe(false)
  })

  it('requires contact_value for direct channels but not for platform', () => {
    expect(sendOfferSchema.safeParse({ ...validForm, contactValue: '' }).success).toBe(false)
    expect(
      sendOfferSchema.safeParse({ ...validForm, contactChannel: 'platform', contactValue: '' })
        .success,
    ).toBe(true)
  })
})

describe('prefill + payload (FE-11)', () => {
  it('prefills salary bounds and type from the position', () => {
    const defaults = prefillFromPosition({
      title: 'Backend Dev',
      salary_min: 220000,
      salary_max: 300000,
      salary_type: 'net',
    })
    expect(defaults.salaryMin).toBe(220000)
    expect(defaults.salaryType).toBe('net')
    const form = buildInitialForm(defaults)
    expect(form.title).toBe('Backend Dev')
    expect(form.expiresInDays).toBe(14)
  })

  it('builds a payload with explicit salary_type and without why_you (B9/B15)', () => {
    const payload = toCreateOfferPayload(
      sendOfferSchema.parse(validForm),
      'pub-anna',
      'pos-1',
    )
    expect(payload.salary_type).toBe('gross')
    expect(payload.candidate_public_id).toBe('pub-anna')
    expect(payload.position_id).toBe('pos-1')
    expect('why_you' in payload).toBe(false)
  })

  it('maps platform channel to a placeholder contact_value', () => {
    const payload = toCreateOfferPayload(
      sendOfferSchema.parse({ ...validForm, contactChannel: 'platform', contactValue: '' }),
      'pub-anna',
    )
    expect(payload.contact_value).toBe('platform')
    expect(payload.position_id).toBeUndefined()
  })
})

describe('mapSendOfferError (FE-11)', () => {
  it('maps 422 salary_invalid to Russian', () => {
    const err = new ApiError({ status: 422, code: 'salary_invalid', detail: 'bad range' })
    expect(mapSendOfferError(err).message).toBe(OFFER_ERROR_MESSAGES.salary_invalid)
  })

  it('maps 403 candidate_not_reachable to Russian', () => {
    const err = new ApiError({ status: 403, code: 'candidate_not_reachable' })
    expect(mapSendOfferError(err).message).toBe(OFFER_ERROR_MESSAGES.candidate_not_reachable)
  })

  it('maps 404 to the pool-not-found hint', () => {
    const err = new ApiError({ status: 404, code: 'not_found' })
    expect(mapSendOfferError(err).message).toBe(OFFER_ERROR_MESSAGES.not_found)
  })

  it('surfaces DRF serializer field errors under the right form keys', () => {
    const err = new ApiError({
      status: 422,
      code: 'validation_failed',
      fieldErrors: { title: ['This field is required.'] },
    })
    const mapped = mapSendOfferError(err)
    expect(mapped.fieldErrors.title).toBe('This field is required.')
    expect(mapped.message).toBe(OFFER_ERROR_MESSAGES.validation_failed)
  })

  it('falls back for non-API errors', () => {
    expect(mapSendOfferError(new Error('network')).message).toBe(
      'Не удалось отправить оффер. Попробуйте ещё раз.',
    )
  })
})

const offer = (status: Offer['status'], extra: Partial<Offer> = {}): Offer =>
  ({ id: `off-${status}`, status, ...extra }) as Offer

describe('board logic (FE-11)', () => {
  it('withdraw is only allowed in sent/viewed', () => {
    expect(canWithdraw(offer('sent'))).toBe(true)
    expect(canWithdraw(offer('viewed'))).toBe(true)
    expect(canWithdraw(offer('accepted'))).toBe(false)
    expect(canWithdraw(offer('expired'))).toBe(false)
  })

  it('contacts appear only while accepted (B16)', () => {
    const contacts = { full_name: 'A', email: 'a@b.c' }
    expect(contactsVisible(offer('accepted', { candidate_contacts: contacts }))).toBe(true)
    expect(contactsVisible(offer('sent', { candidate_contacts: contacts }))).toBe(false)
    expect(contactsVisible(offer('accepted'))).toBe(false)
  })

  it('groups a flat array into the nine status columns', () => {
    const grouped = groupByStatus([
      offer('sent'),
      offer('sent'),
      offer('hired'),
      offer('closed'),
    ])
    expect(Object.keys(grouped)).toHaveLength(9)
    expect(grouped.sent).toHaveLength(2)
    expect(grouped.hired).toHaveLength(1)
    expect(grouped.viewed).toHaveLength(0)
  })
})
