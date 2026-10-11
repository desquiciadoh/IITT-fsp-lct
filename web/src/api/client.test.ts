import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, customFetch } from './client'

function mockResponse(body: unknown, status = 400, contentType = 'application/problem+json') {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': contentType },
  })
}

async function fetchError(): Promise<ApiError> {
  const err = await customFetch('/api/x').catch((e) => e)
  expect(err).toBeInstanceOf(ApiError)
  return err as ApiError
}

describe('customFetch error normalization (BE.md B13/G13)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('does not turn problem metadata into phantom field errors', async () => {
    // A bare problem body (bad credentials) has no `errors`. Normalizing the
    // envelope itself used to put {title, code, detail} into fieldErrors, so
    // applyApiErrorToForm() returned true and the toast was suppressed.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      mockResponse({
        type: 'about:blank',
        title: 'bad_credentials',
        status: 401,
        code: 'bad_credentials',
        detail: 'Неверный email или пароль.',
      }),
    )
    const err = await fetchError()
    expect(err.code).toBe('bad_credentials')
    expect(err.detail).toBe('Неверный email или пароль.')
    expect(err.fieldErrors).toEqual({})
  })

  it('keeps a bare DRF field map when the body is not a problem envelope', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      mockResponse({ email: ['Обязательное поле.'], password: ['Слишком короткий.'] }, 400, 'application/json'),
    )
    const err = await fetchError()
    expect(err.fieldErrors).toEqual({
      email: ['Обязательное поле.'],
      password: ['Слишком короткий.'],
    })
  })

  it('normalizes the contract [{field, msg}] errors list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      mockResponse({ code: 'validation_failed', errors: [{ field: 'salary_min', msg: 'bad' }] }),
    )
    const err = await fetchError()
    expect(err.fieldErrors).toEqual({ salary_min: ['bad'] })
  })
})
