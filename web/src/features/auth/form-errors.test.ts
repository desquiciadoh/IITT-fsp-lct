import { describe, it, expect } from 'vitest'
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { ApiError } from '@/api/client'
import { applyApiErrorToForm } from '@/features/auth/form-errors'

function makeSetError() {
  const calls: { field: string; message: string }[] = []
  const setError = ((field: Path<FieldValues>, opts: { message: string }) => {
    calls.push({ field: String(field), message: opts.message })
  }) as unknown as UseFormSetError<FieldValues>
  return { setError, calls }
}

describe('applyApiErrorToForm', () => {
  it('puts field errors onto matching fields', () => {
    const { setError, calls } = makeSetError()
    const err = new ApiError({
      status: 400,
      code: 'validation_failed',
      fieldErrors: { email: ['Enter a valid email.'], password: ['Too short.'] },
    })
    expect(applyApiErrorToForm(err, setError)).toBe(true)
    expect(calls).toEqual([
      { field: 'email', message: 'Enter a valid email.' },
      { field: 'password', message: 'Too short.' },
    ])
  })

  it('returns false when there are no field errors (caller toasts by code)', () => {
    const { setError, calls } = makeSetError()
    const err = new ApiError({ status: 401, code: 'bad_credentials' })
    expect(applyApiErrorToForm(err, setError)).toBe(false)
    expect(calls).toHaveLength(0)
  })

  it('returns false for non-ApiError', () => {
    const { setError } = makeSetError()
    expect(applyApiErrorToForm(new Error('network down'), setError)).toBe(false)
  })

  it('ignores empty message lists', () => {
    const { setError, calls } = makeSetError()
    const err = new ApiError({ status: 400, code: 'validation_failed', fieldErrors: { email: [] } })
    expect(applyApiErrorToForm(err, setError)).toBe(false)
    expect(calls).toHaveLength(0)
  })
})
