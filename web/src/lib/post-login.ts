import type { Role } from '@/api/types'

/**
 * R20 — resolve the post-login destination from `?next=`.
 *
 * Only same-site, role-appropriate paths are honoured (no open redirect):
 * - must start with a single `/` (`//evil` and absolute URLs are rejected);
 * - candidates/employers may only return to their own area (or `/jury`);
 * - an admin may return anywhere same-site;
 * - anything else falls back to `/`.
 */
export function resolvePostLoginPath(next: string | null | undefined, role?: Role): string {
  const fallback = '/'
  if (!next || !next.startsWith('/') || next.startsWith('//')) return fallback
  if (next === '/') return fallback

  const inArea =
    (role === 'candidate' && (next.startsWith('/candidate') || next.startsWith('/jury'))) ||
    (role === 'employer' && (next.startsWith('/employer') || next.startsWith('/jury'))) ||
    role === 'admin'

  return inArea ? next : fallback
}
