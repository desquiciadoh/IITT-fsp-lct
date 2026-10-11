import { Badge, type BadgeProps } from '@/components/ui/badge'
import { APPLICATION_STATUS_LABEL } from '@/lib/labels'
import type { ApplicationStatus } from '@/api/types'

const VARIANT: Record<ApplicationStatus, NonNullable<BadgeProps['variant']>> = {
  applied: 'info',
  reviewing: 'warning',
  invited: 'default',
  rejected: 'danger',
  hired: 'success',
  withdrawn: 'secondary',
}

export function ApplicationStatusChip({ status }: { status: ApplicationStatus }) {
  return (
    <Badge variant={VARIANT[status] ?? 'outline'}>
      {APPLICATION_STATUS_LABEL[status] ?? status}
    </Badge>
  )
}
