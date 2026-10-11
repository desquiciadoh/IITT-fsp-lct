import { describe, expect, it } from 'vitest'
import { resolvePostLoginPath } from '@/lib/post-login'

describe('resolvePostLoginPath (R20)', () => {
  it('returns the candidate path for a candidate', () => {
    expect(resolvePostLoginPath('/candidate/offers/1', 'candidate')).toBe('/candidate/offers/1')
  })

  it('returns the employer path for an employer', () => {
    expect(resolvePostLoginPath('/employer/positions/9', 'employer')).toBe(
      '/employer/positions/9',
    )
  })

  it('lets a candidate return to the public jury page', () => {
    expect(resolvePostLoginPath('/jury', 'candidate')).toBe('/jury')
  })

  it('rejects a cross-area path', () => {
    expect(resolvePostLoginPath('/employer/positions/9', 'candidate')).toBe('/')
  })

  it('rejects protocol-relative open redirects', () => {
    expect(resolvePostLoginPath('//evil.example', 'admin')).toBe('/')
  })

  it('rejects absolute URLs', () => {
    expect(resolvePostLoginPath('https://evil.example', 'admin')).toBe('/')
  })

  it('rejects URLs not starting with a slash', () => {
    expect(resolvePostLoginPath('candidate', 'candidate')).toBe('/')
  })

  it('falls back to / for missing next', () => {
    expect(resolvePostLoginPath(null, 'candidate')).toBe('/')
    expect(resolvePostLoginPath(undefined, 'candidate')).toBe('/')
  })

  it('lets an admin go anywhere same-site', () => {
    expect(resolvePostLoginPath('/lab', 'admin')).toBe('/lab')
  })

  it('renders the root as the fallback', () => {
    expect(resolvePostLoginPath('/', 'candidate')).toBe('/')
  })
})
