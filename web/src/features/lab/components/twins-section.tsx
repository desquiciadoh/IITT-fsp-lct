import { FileStack } from 'lucide-react'
import { useLabTwins } from '@/api/lab'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { Button } from '@/components/ui/button'
import { RowSkeleton } from '@/components/ui/skeleton'
import { DifficultyBars } from '@/features/lab/components/difficulty-bars'
import { TwinInstanceCard } from '@/features/lab/components/twin-instance-card'
import { GRADE_LABEL } from '@/lib/labels'

const dateFmt = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })

/**
 * FE-14: JD → blueprint → two unique instances with the same difficulty
 * profile. Mocked (G21/BE-22); slot for the position page link at /lab#twins.
 */
export function TwinsSection({ positionId = 'pos-1' }: { positionId?: string }) {
  const { data, isLoading, isError, error, refetch } = useLabTwins(positionId)

  if (isLoading) return <RowSkeleton count={2} />

  if (isError || !data) {
    const message =
      error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось загрузить близнецов.'
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Повторить
        </Button>
      </div>
    )
  }

  const { blueprint, instances } = data

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <FileStack className="h-4 w-4" /> Blueprint
        </span>
        <p className="text-sm">
          {blueprint.derived_from} · целевой грейд <b>{GRADE_LABEL[blueprint.target_grade]}</b>
        </p>
        <ul className="flex flex-wrap gap-1.5">
          {blueprint.requirements.map((req, index) => (
            <li key={index} className="rounded-md border border-border bg-secondary px-2 py-0.5 text-xs">
              {req}
            </li>
          ))}
        </ul>
        <div className="mt-1 max-w-xs">
          <DifficultyBars profile={blueprint.difficulty} />
        </div>
        <span className="text-xs text-muted-foreground">
          Сгенерировано: {dateFmt.format(new Date(data.generated_at))}
        </span>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        {instances.map((instance) => (
          <TwinInstanceCard key={instance.id} instance={instance} />
        ))}
      </div>
    </div>
  )
}