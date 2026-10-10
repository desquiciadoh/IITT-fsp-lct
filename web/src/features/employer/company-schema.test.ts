import { describe, it, expect } from 'vitest'
import { companySchema, toCompanyInput } from './company-schema'

const valid = {
  name: 'ООО Ромашка',
  inn: '7701234567',
  website: 'https://example.ru',
  email_domain: 'example.ru',
  business_domain: 'Финтех',
  description: 'Платёжный стартап',
  contact_email: 'hr@example.ru',
}

describe('companySchema (FE-09 stage 1)', () => {
  it('accepts a full valid payload', () => {
    expect(companySchema.safeParse(valid).success).toBe(true)
  })

  it('accepts only the required fields with empty optionals', () => {
    const result = companySchema.safeParse({ ...valid, inn: '', website: '', email_domain: '' })
    expect(result.success).toBe(true)
  })

  it('rejects an empty company name', () => {
    const result = companySchema.safeParse({ ...valid, name: '   ' })
    expect(result.success).toBe(false)
  })

  it('rejects an invalid INN (not 10/12 digits)', () => {
    for (const inn of ['123', '770123456', '77012345678', 'abcdefghij']) {
      const result = companySchema.safeParse({ ...valid, inn })
      expect(result.success, `inn=${inn}`).toBe(false)
    }
  })

  it('rejects a website without scheme and a malformed email domain', () => {
    expect(companySchema.safeParse({ ...valid, website: 'example.ru' }).success).toBe(false)
    expect(companySchema.safeParse({ ...valid, email_domain: 'not a domain' }).success).toBe(false)
  })

  it('rejects an invalid contact email', () => {
    expect(companySchema.safeParse({ ...valid, contact_email: 'hr@' }).success).toBe(false)
  })

  it('toCompanyInput strips empty optional strings to undefined', () => {
    const parsed = companySchema.parse({ ...valid, inn: '', website: '' })
    const body = toCompanyInput(parsed)
    expect(body.name).toBe('ООО Ромашка')
    expect(body.inn).toBeUndefined()
    expect(body.website).toBeUndefined()
    expect(body.contact_email).toBe('hr@example.ru')
  })
})
