import { APPLICATION_STATUS_LABEL } from '@/lib/labels'
import type { ApplicationStatus } from '@/api/types'

const COLOR: Record<ApplicationStatus, string> = {
  applied: 'text-info',
  reviewing: 'text-warn',
  interview: 'text-primary',
  offer: 'text-plus',
  rejected: 'text-minus',
  withdrawn: 'text-muted-foreground',
}

/** FE-15: application pipeline status chip (candidate + employer views). */
export function ApplicationStatusChip({ status }: { status: ApplicationStatus }) {
  const label = APPLICATION_STATUS_LABEL[status] ?? status
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border border-border bg-secondary px-2 py-0.5 text-xs ${COLOR[status]}`}
      aria-label={`Статус отклика: ${label}`}
    >
      <span className={`size-1.5 rounded-full bg-current ${status === 'withdrawn' ? 'opacity-50' : ''}`} />
      {label}
    </span>
  )
}