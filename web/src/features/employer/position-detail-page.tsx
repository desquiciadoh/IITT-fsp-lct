import { useParams, useSearchParams } from 'react-router-dom'
import { usePosition } from '@/api/employer'
import { ApiError } from '@/api/client'
import { PositionForm, positionToForm } from '@/features/employer/position-form'
import { PoolTab } from '@/features/employer/pool-tab'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState, EmptyState } from '@/components/domain/states'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip } from '@/components/domain/status-chip'
import { cn } from '@/lib/utils'

/**
 * FE-09 · settings tab (GET/PUT /api/positions/{id}) + FE-10 · scouting pool
 * tab (`/employer/positions/:id`). The active tab lives in `?tab=` so a
 * reload restores the whole view; pool filters and the candidate drawer are
 * URL-synced inside PoolTab (?c=<public_id>).
 */
const TABS = [
  { key: 'pool', label: 'Пуул' },
  { key: 'settings', label: 'Настройки' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function PositionDetailPage() {
  const { id = '' } = useParams()
  const [searchParams] = useSearchParams()
  const { data: position, isLoading, isError, error, refetch } = usePosition(id)

  if (isLoading) return <Skeleton className="h-64 rounded-xl" />
  if (isError || !position) {
    const notFound = error instanceof ApiError && error.code === 'not_found'
    if (notFound) return <EmptyState title="Вакансия не найдена" description="Она удалена или недоступна." />
    return <ErrorState code={error instanceof ApiError ? error.code : undefined} onRetry={() => void refetch()} />
  }

  const tab: TabKey = TABS.some((x) => x.key === searchParams.get('tab'))
    ? (searchParams.get('tab') as TabKey)
    : 'pool'

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{position.title}</h1>
        <span className="flex items-center gap-2">
          <StatusChip status={(position.status ?? 'draft') as never} />
          <SalaryTag min={position.salary_min} max={position.salary_max} type={position.salary_type} emphasize />
        </span>
      </div>
      <PositionTabs current={tab} />
      {tab === 'pool' ? (
        <PoolTab positionId={position.id} specialization={position.specialization} position={position} />
      ) : (
        <Card className="mx-auto w-full max-w-2xl">
          <CardHeader>
            <CardTitle className="text-base">Настройки вакансии</CardTitle>
          </CardHeader>
          <CardContent>
            <PositionForm key={position.id} mode="edit" positionId={position.id} defaultValues={positionToForm(position)} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function PositionTabs({ current }: { current: TabKey }) {
  return (
    <div role="tablist" aria-label="Разделы вакансии" className="flex gap-1 border-b border-border">
      {TABS.map((tab) => (
        <a
          key={tab.key}
          role="tab"
          aria-selected={current === tab.key}
          href={`?${withTab(tab.key)}`}
          className={cn(
            '-mb-px rounded-t-lg border-b-2 px-4 py-2 text-sm transition-colors',
            current === tab.key
              ? 'border-primary font-semibold text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          {tab.label}
        </a>
      ))}
    </div>
  )
}

/** Switch tab while keeping every other query param (filters, ?c=…). */
function withTab(tab: TabKey): string {
  const params = new URLSearchParams(window.location.search)
  params.set('tab', tab)
  return params.toString()
}
