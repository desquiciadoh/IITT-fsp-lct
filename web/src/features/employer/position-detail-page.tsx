import { useParams } from 'react-router-dom'
import { usePosition } from '@/api/employer'
import { ApiError } from '@/api/client'
import { PositionForm, positionToForm } from '@/features/employer/position-form'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState, EmptyState } from '@/components/domain/states'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip } from '@/components/domain/status-chip'

/**
 * FE-09 · Position detail (`/employer/positions/:id`) — settings tab with
 * GET/PUT /api/positions/{id}. FE-10 (scouting pool) will add tabs here.
 */
export function PositionDetailPage() {
  const { id = '' } = useParams()
  const { data: position, isLoading, isError, error, refetch } = usePosition(id)

  if (isLoading) return <Skeleton className="h-64 rounded-xl" />
  if (isError || !position) {
    const notFound = error instanceof ApiError && error.code === 'not_found'
    if (notFound) return <EmptyState title="Вакансия не найдена" description="Она удалена или недоступна." />
    return <ErrorState code={error instanceof ApiError ? error.code : undefined} onRetry={() => void refetch()} />
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{position.title}</h1>
        <span className="flex items-center gap-2">
          <StatusChip status={position.status ?? 'open'} />
          <SalaryTag min={position.salary_min} max={position.salary_max} type={position.salary_type} emphasize />
        </span>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Настройки вакансии</CardTitle>
        </CardHeader>
        <CardContent>
          <PositionForm key={position.id} mode="edit" positionId={position.id} defaultValues={positionToForm(position)} />
        </CardContent>
      </Card>
    </div>
  )
}
