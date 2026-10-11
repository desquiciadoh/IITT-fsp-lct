import { ApiError } from '@/api/client'

/**
 * R21 — query retry policy. A dead session (401) or a forbidden request (403)
 * must never be retried: retrying would fire duplicate toasts/navigations
 * before the redirect lands. Everything else is retried at most once.
 */
export function shouldRetryRequest(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return false
  }
  return failureCount < 1
}
