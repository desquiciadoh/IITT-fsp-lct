import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { ApiError } from '@/api/client'

/**
 * Maps ApiError.fieldErrors (both backend shapes, already normalized in
 * client.ts) onto react-hook-form fields.
 * Returns true when at least one field got an error — the caller then skips
 * the generic toast (FE-02).
 */
export function applyApiErrorToForm<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
): boolean {
  if (!(error instanceof ApiError)) return false
  let applied = false
  for (const [field, messages] of Object.entries(error.fieldErrors)) {
    const message = messages[0]
    if (message) {
      setError(field as Path<T>, { type: 'server', message })
      applied = true
    }
  }
  return applied
}
