import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, Send } from 'lucide-react'
import { toast } from 'sonner'
import { useMicroTask, useMyDrops, useSubmitMicroTask } from '@/api/microtasks'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { EmptyState } from '@/components/domain/states'
import { Button } from '@/components/ui/button'
import { RowSkeleton } from '@/components/ui/skeleton'
import { MICROTASK_FORMAT_LABEL, MICROTASK_REVIEW_LABEL, SPEC_LABEL } from '@/lib/labels'

/** FE-16 candidate solve screen: text answer, auto tasks are scored instantly. */
export function MicrotaskSolvePage() {
  const { id } = useParams()
  const [answer, setAnswer] = useState('')

  const { data: task, isLoading, isError } = useMicroTask(id ?? '')
  const { data: drops } = useMyDrops()
  const submit = useSubmitMicroTask(id ?? '')

  const drop = drops?.find((d) => d.task.id === id)

  if (isLoading) return <RowSkeleton count={3} />
  if (isError || !task)
    return <EmptyState title="Задача не найдена" description="Возможно, она снята с публикации." />

  const scored = drop?.score !== null && drop?.score !== undefined
  const statusLabel = scored ? `Оценка: ${drop?.score}/5` : MICROTASK_REVIEW_LABEL.pending

  const handleSubmit = () =>
    submit.mutate(answer, {
      onSuccess: () => {
        toast.success(task.format === 'auto' ? 'Решение проверено автоматически' : 'Решение отправлено на ревью')
        setAnswer('')
      },
      onError: (error) =>
        toast.error(
          error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось отправить решение.',
        ),
    })

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {task.company.name} · {SPEC_LABEL[task.specialization]} ·{' '}
          {MICROTASK_FORMAT_LABEL[task.format]}
        </span>
        <h1 className="text-2xl font-bold">{task.title}</h1>
        <p className="text-sm text-muted-foreground">
          Срок — до {new Date(task.deadline).toLocaleDateString('ru-RU')}. Одно решение на задачу:
          повторная отправка заменяет прошлое.
        </p>
      </header>

      <div className="rounded-xl border border-border bg-card p-5">
        <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-foreground">
          {task.prompt_md}
        </pre>
      </div>

      {drop ? (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-plus">
            <CheckCircle2 className="h-4 w-4" /> {statusLabel}
          </span>
          <div className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Ваш ответ</span>
            <pre className="whitespace-pre-wrap font-sans text-sm text-muted-foreground">
              {String(drop.answer)}
            </pre>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
          <label htmlFor="microtask-answer" className="text-xs uppercase tracking-wide text-muted-foreground">
            Ваш ответ
          </label>
          <textarea
            id="microtask-answer"
            rows={8}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Опишите решение — код, SQL, псевдокод или рассуждение…"
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              {task.format === 'auto'
                ? 'Проверка автоматическая, результат мгновенный.'
                : 'Ответ уйдёт на ревью компании.'}
            </span>
            <Button disabled={!answer.trim() || submit.isPending} onClick={handleSubmit}>
              <Send className="h-4 w-4" /> Отправить
            </Button>
          </div>
          {submit.isError && (
            <p className="text-sm text-destructive">
              {submit.error instanceof ApiError
                ? errorMessage(submit.error.code, submit.error.detail)
                : 'Не удалось отправить решение.'}
            </p>
          )}
        </div>
      )}
    </section>
  )
}