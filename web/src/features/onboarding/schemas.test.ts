import { describe, it, expect } from 'vitest'
import { surveySchema, consentSchema } from '@/features/onboarding/schemas'

const valid = {
  specialization: 'backend' as const,
  years_experience: 3,
  roles: ['developer'],
  work_formats: ['hybrid' as const],
  salary_min: 200000,
  salary_max: 300000,
  salary_type: 'gross' as const,
  salary_floor: 180000,
  about: 'Привет',
}

describe('surveySchema', () => {
  it('accepts a valid survey', () => {
    expect(surveySchema.safeParse(valid).success).toBe(true)
  })

  it('rejects salary_min > salary_max with an error on salary_max', () => {
    const result = surveySchema.safeParse({ ...valid, salary_min: 500000 })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(['salary_max'])
    }
  })

  it('requires a specialization', () => {
    const result = surveySchema.safeParse({ ...valid, specialization: undefined })
    expect(result.success).toBe(false)
  })

  it('requires at least one work format', () => {
    const result = surveySchema.safeParse({ ...valid, work_formats: [] })
    expect(result.success).toBe(false)
  })

  it('requires at least one role', () => {
    const result = surveySchema.safeParse({ ...valid, roles: [] })
    expect(result.success).toBe(false)
  })
})

describe('consentSchema', () => {
  it('blocks without processing consent', () => {
    expect(
      consentSchema.safeParse({ processing: false, publication: true, fsp_sync: true })
        .success,
    ).toBe(false)
  })
  it('allows with processing only', () => {
    expect(
      consentSchema.safeParse({ processing: true, publication: false, fsp_sync: false })
        .success,
    ).toBe(true)
  })
})
