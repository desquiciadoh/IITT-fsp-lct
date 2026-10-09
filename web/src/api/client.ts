/**
 * Shared fetch mutator for orval-generated calls and hand-written queries.
 *
 * - same-origin `/api/...` requests with cookies;
 * - `X-CSRFToken` (read from the `csrftoken` cookie) on unsafe methods;
 * - non-2xx → thrown `ApiError` normalized from every shape the Django
 *   backend emits today (BE.md B13/G13).
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly title?: string
  readonly detail?: string
  /** field name → list of messages (always normalized to this shape) */
  readonly fieldErrors: Record<string, string[]>

  constructor(init: {
    status: number
    code: string
    title?: string
    detail?: string
    fieldErrors?: Record<string, string[]>
  }) {
    super(init.detail ?? init.title ?? init.code)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.title = init.title
    this.detail = init.detail
    this.fieldErrors = init.fieldErrors ?? {}
  }
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

let csrfPriming: Promise<void> | null = null

/** Best effort: Django sets the cookie after login; GET /api/auth/csrf is gap G1. */
async function ensureCsrfCookie(): Promise<void> {
  if (readCookie('csrftoken')) return
  if (!csrfPriming) {
    csrfPriming = fetch('/api/auth/csrf', { credentials: 'include' })
      .catch(() => undefined)
      .then(() => {
        csrfPriming = null
      })
  }
  await csrfPriming
}

type ProblemBody = {
  type?: string
  title?: string
  status?: number
  code?: string
  detail?: string
  errors?: unknown
  detail_raw?: unknown
}

function normalizeFieldErrors(raw: unknown): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  if (!raw) return out
  if (Array.isArray(raw)) {
    // [{field, msg}] — contract shape
    for (const item of raw) {
      if (item && typeof item === 'object' && 'field' in item) {
        const field = String((item as { field: unknown }).field)
        const msg = String((item as { msg?: unknown }).msg ?? '')
        ;(out[field] ??= []).push(msg)
      }
    }
    return out
  }
  if (typeof raw === 'object') {
    // {field: [msg, ...]} — DRF serializer shape the backend also emits
    for (const [field, value] of Object.entries(raw as Record<string, unknown>)) {
      if (Array.isArray(value)) out[field] = value.map(String)
      else if (value != null) out[field] = [String(value)]
    }
  }
  return out
}

function toApiError(status: number, body: unknown): ApiError {
  const problem = (body ?? {}) as ProblemBody
  const detail = typeof problem.detail === 'string' ? problem.detail : undefined
  // Python repr junk like "{'detail': ErrorDetail(...)}" — not for humans.
  const junkDetail = detail?.startsWith("{'") || detail?.startsWith('{"')
  const code =
    problem.code ??
    (status === 401
      ? 'unauthorized'
      : status === 403
        ? 'forbidden'
        : status === 404
          ? 'not_found'
          : status === 409
            ? 'version_conflict'
            : status === 422
              ? 'validation_failed'
              : 'api_error')
  return new ApiError({
    status,
    code,
    title: problem.title,
    detail: junkDetail ? undefined : detail,
    fieldErrors: normalizeFieldErrors(problem.errors ?? (junkDetail ? undefined : body)),
  })
}

export const customFetch = async <T>(
  url: string,
  options: RequestInit = {},
): Promise<T> => {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')

  if (UNSAFE.has(method)) {
    await ensureCsrfCookie()
    const token = readCookie('csrftoken')
    if (token) headers.set('X-CSRFToken', token)
  }

  const res = await fetch(url, { ...options, headers, credentials: 'include' })

  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') ?? ''
  const isJson =
    contentType.includes('json') && !contentType.includes('text/html')

  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text()
    throw toApiError(res.status, body)
  }
  if (!isJson) return (await res.text()) as unknown as T
  if (res.headers.get('content-length') === '0') return undefined as T
  return (await res.json()) as T
}
