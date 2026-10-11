import type { ApplicationStatus } from '@/api/types'

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'applied',
  'reviewing',
  'invited',
  'rejected',
  'hired',
  'withdrawn',
]

/** Mirrors the backend transition map (matching/views.py, FE-15). */
export const APPLICATION_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  applied: ['reviewing', 'invited', 'rejected'],
  reviewing: ['invited', 'rejected'],
  invited: ['hired', 'rejected'],
  rejected: [],
  hired: [],
  withdrawn: [],
}

export function nextStatuses(status: ApplicationStatus): ApplicationStatus[] {
  return APPLICATION_TRANSITIONS[status] ?? []
}

/** The candidate may withdraw until the process is finished. */
export function canWithdraw(status: ApplicationStatus): boolean {
  return !['withdrawn', 'rejected', 'hired'].includes(status)
}

/** Statuses an employer can set from the pipeline (no transitions to itself). */
export function employerActions(status: ApplicationStatus): ApplicationStatus[] {
  return nextStatuses(status)
}
