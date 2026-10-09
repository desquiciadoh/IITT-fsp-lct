import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import { retryQuery } from '@/api/retry'

describe('retryQuery (R21)', () => {
  it('never retries an expired or forbidden session', () => {
    expect(retryQuery(0, new ApiError({ status: 401, code: 'unauthorized' }))).toBe(false)
    expect(retryQuery(0, new ApiError({ status: 403, code: 'forbidden' }))).toBe(false)
  })

  it('retries every other failure exactly once', () => {
    expect(retryQuery(0, new Error('boom'))).toBe(true)
    expect(retryQuery(1, new Error('boom'))).toBe(false)
    expect(retryQuery(0, new ApiError({ status: 500, code: 'api_error' }))).toBe(true)
    expect(retryQuery(1, new ApiError({ status: 500, code: 'api_error' }))).toBe(false)
  })
})
