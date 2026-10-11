import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { usePositionApplications, useUpdateApplicationStatus } from '@/api/vacancies'
import type { ApplicationEmployer, ApplicationStatus } from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { APPLICATION_STATUS_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { ApplicationStatusChip } from '@/components/domain/application-status-chip'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import { employerActions } from '@/features/vacancies/status'

function ApplicantRow({
  application,
  onMove,
  pending,
}: {
  application: ApplicationEmployer
  onMove: (status: ApplicationStatus) => void
  pending: boolean
}) {
  const name = application.candidate?.display_name ?? application.candidate?.public_id ?? 'Кандидат'
  const actions = employerActions(application.status)

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col">
          <span className="font-semibold">{name}</span>
          {application.candidate?.public_id && (
            <span className="font-mono text-xs text-muted-foreground">
              {application.candidate.public_id}
            </span>
          )}
        </div>
        <ApplicationStatusChip status={application.status} />
      </div>
      {application.note && <p className="text-sm text-muted-foreground">{application.note}</p>}
      {actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {actions.map((status) => (
            <Button
              key={status}
              size="sm"
              variant={status === 'rejected' ? 'outline' : 'default'}
              disabled={pending}
              onClick={() => onMove(status)}
            >
              {APPLICATION_STATUS_LABEL[status] ?? status}
            </Button>
          ))}
        </div>
      )}
    </div>
  )
}

export function PositionApplicantsTab({ positionId }: { positionId: string }) {
  const { data, isLoading, isError, refetch } = usePositionApplications(positionId)
  const update = useUpdateApplicationStatus(positionId)

  const move = (id: string, status: ApplicationStatus) => {
    update.mutate(
      { id, status },
      {
        onSuccess: () => toast.success(`Статус: ${APPLICATION_STATUS_LABEL[status] ?? status}`),
        onError: (error) =>
          toast.error(
            error instanceof ApiError
              ? errorMessage(error.code, error.detail)
              : 'Не удалось обновить статус.',
          ),
      },
    )
  }

  if (isLoading) return <RowSkeleton count={3} />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="Откликов пока нет"
        description="Кандидаты появятся здесь, когда откликнутся на вакансию."
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {data.map((application) => (
        <ApplicantRow
          key={application.id}
          application={application}
          pending={update.isPending}
          onMove={(status) => move(application.id, status)}
        />
      ))}
    </div>
  )
}
