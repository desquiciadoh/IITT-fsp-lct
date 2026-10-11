import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft } from 'lucide-react'
import { ApiError } from '@/api/client'
import { useMyMicroTasks, useSubmitMicroTask } from '@/api/microtasks'
import { errorMessage } from '@/i18n/errors'
import { MICROTASK_FORMAT_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import {
  DROP_STAGE_LABEL,
  deadlinePassed,
  dropStage,
  scoreText,
} from '@/features/microtasks/format'

export function TaskSolvePage() {
  const { dropId } = useParams<{ dropId: string }>()
  const { data: drops, isLoading, isError, refetch } = useMyMicroTasks()
  const submit = useSubmitMicroTask(dropId ?? '')
  const [answer, setAnswer] = useState('')

  if (isLoading) return <RowSkeleton count={3} />
  if (isError) return <ErrorState onRetry={() => void refetch()} />

  const drop = drops?.find((d) => d.id === dropId)
  if (!drop) return <ErrorState onRetry={() => void refetch()} />

  const stage = dropStage(drop)
  const passed = deadlinePassed(drop.task.deadline)
  const locked = stage !== 'pending' || passed

  const send = () => {
    if (!answer.trim()) return
    submit.mutate(answer, {
      onSuccess: (updated) => {
        toast.success(
          updated.score != null ? `Проверено: ${scoreText(updated.score)}` : 'Решение отправлено',
        )
        setAnswer('')
      },
      onError: (error) =>
        toast.error(
          error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось отправить.',
        ),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/candidate/micro-tasks"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Все задачи
      </Link>

      <Card className="gap-4 py-5">
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-col gap-1">
              <h1 className="text-lg font-semibold">{drop.task.title}</h1>
              <span className="text-sm text-muted-foreground">
                {drop.task.company?.name} ·{' '}
                {MICROTASK_FORMAT_LABEL[drop.task.format] ?? drop.task.format}
              </span>
            </div>
            <Badge variant={locked ? 'outline' : 'warning'}>{DROP_STAGE_LABEL[stage]}</Badge>
          </div>

          <div className="rounded-lg border border-border bg-background p-4">
            <pre className="whitespace-pre-wrap font-sans text-sm">{drop.task.prompt_md}</pre>
          </div>

          {stage === 'pending' && !passed && (
            <>
              <label className="flex flex-col gap-1 text-sm font-medium">
                Ваше решение
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  rows={6}
                  placeholder="Опишите подход или пришлите решение"
                  className="rounded-md border border-input bg-card px-3 py-2 text-sm"
                />
              </label>
              <div>
                <Button disabled={submit.isPending || !answer.trim()} onClick={send}>
                  {submit.isPending ? 'Отправляем…' : 'Отправить решение'}
                </Button>
              </div>
            </>
          )}

          {stage !== 'pending' && (
            <div className="flex flex-col gap-1 rounded-lg border border-border bg-background p-4 text-sm">
              {stage === 'review' ? (
                <p>Решение отправлено. Работодатель скоро поставит оценку.</p>
              ) : (
                <p>
                  Результат: <b>{scoreText(drop.score)}</b>
                  {drop.employer_rating != null && ` · оценка работодателя: ${drop.employer_rating}/5`}
                </p>
              )}
            </div>
          )}

          {passed && stage === 'pending' && (
            <p className="text-sm text-destructive">Срок выполнения задачи вышел.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}