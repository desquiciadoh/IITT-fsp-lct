import type { Me } from '@/api/types'

const AREA: Partial<Record<Me['role'], string>> = {
  candidate: '/candidate',
  employer: '/employer',
}

/**
 * Post-login destination from `?next=` (R20).
 *
 * Only same-origin paths inside the user's own role area are honored. Anything
 * else — external URLs, protocol-relative `//host`, another role's area, or an
 * unknown role — falls back to `/`.
 */
export function resolveNext(next: string | null | undefined, role: Me['role']): string {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return '/'
  const area = AREA[role]
  if (!area) return '/'
  return next === area || next.startsWith(`${area}/`) ? next : '/'
}
