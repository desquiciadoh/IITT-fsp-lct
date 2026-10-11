import { describe, expect, it } from 'vitest'
import { shouldRetryRequest } from '@/api/retry'
import { ApiError } from '@/api/client'

describe('shouldRetryRequest (R21)', () => {
  it('retries a generic failure once', () => {
    expect(shouldRetryRequest(0, new Error('boom'))).toBe(true)
  })

  it('stops retrying after the first attempt', () => {
    expect(shouldRetryRequest(1, new Error('boom'))).toBe(false)
  })

  it('never retries a 401 (dead session)', () => {
    const err = new ApiError({ status: 401, code: 'unauthorized', detail: 'nope' })
    expect(shouldRetryRequest(0, err)).toBe(false)
  })

  it('never retries a 403', () => {
    const err = new ApiError({ status: 403, code: 'forbidden', detail: 'no' })
    expect(shouldRetryRequest(0, err)).toBe(false)
  })

  it('still retries other ApiErrors once', () => {
    const err = new ApiError({ status: 500, code: 'server_error', detail: 'boom' })
    expect(shouldRetryRequest(0, err)).toBe(true)
    expect(shouldRetryRequest(1, err)).toBe(false)
  })
})
