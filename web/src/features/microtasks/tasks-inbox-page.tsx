import { Link } from 'react-router-dom'
import { ArrowRight, Clock } from 'lucide-react'
import { useMyMicroTasks } from '@/api/microtasks'
import { MICROTASK_FORMAT_LABEL } from '@/lib/labels'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import {
  DROP_STAGE_LABEL,
  deadlinePassed,
  dropStage,
  scoreText,
  type DropStage,
} from '@/features/microtasks/format'
import type { MicroTaskDropCandidate } from '@/api/types'

const STAGE_VARIANT: Record<DropStage, 'outline' | 'warning' | 'success'> = {
  pending: 'outline',
  review: 'warning',
  rated: 'success',
}

function DropCard({ drop }: { drop: MicroTaskDropCandidate }) {
  const stage = dropStage(drop)
  const passed = deadlinePassed(drop.task.deadline)

  return (
    <Card className="gap-4 py-5">
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold">{drop.task.title}</h2>
            <span className="text-sm text-muted-foreground">{drop.task.company?.name}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">
              {MICROTASK_FORMAT_LABEL[drop.task.format] ?? drop.task.format}
            </Badge>
            <Badge variant={STAGE_VARIANT[stage]}>{DROP_STAGE_LABEL[stage]}</Badge>
          </div>
        </div>
        {drop.task.deadline && (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {passed ? 'срок вышел' : `до ${new Date(drop.task.deadline).toLocaleString('ru-RU')}`}
          </span>
        )}
        {stage === 'rated' ? (
          <p className="text-sm text-muted-foreground">
            Результат: {scoreText(drop.score)}
            {drop.employer_rating != null && ` · оценка работодателя: ${drop.employer_rating}/5`}
          </p>
        ) : stage === 'review' ? (
          <p className="text-sm text-muted-foreground">Решение отправлено, ждём оценки работодателя.</p>
        ) : (
          <p className="text-sm text-muted-foreground">Возьмите задачу и пришлите решение.</p>
        )}
        <Link
          to={`/candidate/micro-tasks/${drop.id}`}
          className="inline-flex items-center gap-1 text-sm underline underline-offset-4"
        >
          {stage === 'pending' ? 'Решить' : 'Смотреть решение'}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </CardContent>
    </Card>
  )
}

export function TasksInboxPage() {
  const { data, isLoading, isError, refetch } = useMyMicroTasks()

  if (isLoading) return <RowSkeleton count={3} />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="Задач пока нет"
        description="Работодатели присылают микрозадачи, чтобы проверить вас на реальном кейсе. Они появятся здесь."
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold">Микрозадачи</h1>
      <div className="grid gap-3">
        {data.map((drop) => (
          <DropCard key={drop.id} drop={drop} />
        ))}
      </div>
    </div>
  )
}