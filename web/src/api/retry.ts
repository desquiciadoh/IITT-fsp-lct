import { ApiError } from '@/api/client'

/**
 * Query retry policy (R21).
 *
 * An expired or forbidden session must not be retried — the global handler
 * clears the cache and redirects to `/login`, so a retry only duplicates the
 * request and the toast. Every other failure gets the usual single retry.
 */
export function retryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return false
  return failureCount < 1
}
