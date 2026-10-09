import { describe, expect, it } from 'vitest'
import { resolveNext } from '@/features/auth/next-route'

describe('resolveNext (R20)', () => {
  it('honors a path inside the candidate area', () => {
    expect(resolveNext('/candidate/offers/off-1', 'candidate')).toBe('/candidate/offers/off-1')
  })

  it('honors the exact area root', () => {
    expect(resolveNext('/candidate', 'candidate')).toBe('/candidate')
    expect(resolveNext('/employer', 'employer')).toBe('/employer')
  })

  it('rejects protocol-relative and external URLs', () => {
    expect(resolveNext('//evil.example.com', 'candidate')).toBe('/')
    expect(resolveNext('https://evil.example.com', 'candidate')).toBe('/')
  })

  it('rejects another role area', () => {
    expect(resolveNext('/employer/offers', 'candidate')).toBe('/')
    expect(resolveNext('/candidate/offers', 'employer')).toBe('/')
  })

  it('falls back to / without a usable next', () => {
    expect(resolveNext(null, 'candidate')).toBe('/')
    expect(resolveNext(undefined, 'employer')).toBe('/')
    expect(resolveNext('/jury', 'candidate')).toBe('/')
  })
})
