import { Eye, EyeOff, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import {
  usePosition,
  usePositionApplications,
  useSetApplicationStatus,
  useSetPositionPublic,
} from '@/api/vacancies'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { ApplicationStatusChip } from '@/components/domain/application-status-chip'
import { Button } from '@/components/ui/button'
import { RowSkeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/domain/states'
import type { ApplicationStatus } from '@/api/types'

const STATUS_FLOW: ApplicationStatus[] = ['applied', 'reviewing', 'interview', 'offer', 'rejected']

/**
 * FE-15 employer part: publish toggle + applicant pipeline. Slots into FE2's
 * position page (`/employer/positions/:id`) when FE-10 lands; previewed at
 * `/dev/vacancies-employer` until then.
 */
export function EmployerVacancyPanel({ positionId }: { positionId: string }) {
  const { data: position, isLoading: positionLoading } = usePosition(positionId)
  const { data: applications, isLoading: appsLoading, isError, refetch } = usePositionApplications(positionId)
  const setStatus = useSetApplicationStatus()
  const setPublic = useSetPositionPublic(positionId)

  const handleError = (error: unknown) =>
    toast.error(
      error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось выполнить запрос.',
    )

  const togglePublic = () => {
    if (!position) return
    setPublic.mutate(!(position.is_public ?? true), {
      onSuccess: () =>
        toast.success(position.is_public ? 'Вакансия скрыта из публичного списка' : 'Вакансия опубликована'),
      onError: handleError,
    })
  }

  if (positionLoading || appsLoading) return <RowSkeleton count={3} />

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold">{position?.title ?? 'Вакансия'}</h2>
          <span className="text-xs text-muted-foreground">
            {applications?.length ?? 0} откликов · панель для страницы позиции (FE2, FE-10)
          </span>
        </div>
        <Button variant="outline" size="sm" disabled={setPublic.isPending} onClick={togglePublic}>
          {position?.is_public ?? true ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          {position?.is_public ?? true ? 'Скрыть вакансию' : 'Опубликовать'}
        </Button>
      </header>

      {isError ? (
        <p className="text-sm text-destructive">
          Не удалось загрузить отклики.{' '}
          <button className="underline underline-offset-4" onClick={() => void refetch()}>
            Повторить
          </button>
        </p>
      ) : applications && applications.length > 0 ? (
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Отклики на вакансию</caption>
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="py-2 pr-4 font-medium">
                Кандидат
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Статус
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Действие
              </th>
            </tr>
          </thead>
          <tbody>
            {applications.map((application) => (
              <tr key={application.id} className="border-b border-border last:border-0">
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-2 font-mono text-xs">
                    <UserPlus className="h-4 w-4 text-muted-foreground" />
                    {application.candidate.display_name}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {application.candidate.public_id}
                    {application.candidate.city ? ` · ${application.candidate.city}` : ''}
                  </span>
                </td>
                <td className="py-2 pr-4">
                  <ApplicationStatusChip status={application.status} />
                </td>
                <td className="py-2 pr-2">
                  <select
                    aria-label={`Статус отклика ${application.candidate.display_name}`}
                    value={application.status}
                    disabled={setStatus.isPending}
                    onChange={(e) =>
                      setStatus.mutate(
                        { id: application.id, status: e.target.value as ApplicationStatus },
                        { onError: handleError },
                      )
                    }
                    className="rounded-md border border-border bg-background px-2 py-1 text-xs"
                  >
                    {STATUS_FLOW.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState
          title="Откликов пока нет"
          description="Как только кандидат откликнется, он появится здесь — отклик открывает контакты."
        />
      )}
    </section>
  )
}