import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Clock3 } from 'lucide-react'
import { useMicroTasks, useMyDrops } from '@/api/microtasks'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { TrustBadge } from '@/components/domain/trust-badge'
import { Button } from '@/components/ui/button'
import { RowSkeleton } from '@/components/ui/skeleton'
import { GRADE_LABEL, MICROTASK_FORMAT_LABEL, SPEC_LABEL } from '@/lib/labels'
import type { MicroTask, MicroTaskDrop } from '@/api/types'

/** FE-16 candidate inbox: tasks that are open, not expired and not yet solved. */
export function MicrotaskInboxPage() {
  const { data: tasks, isLoading, isError, refetch } = useMicroTasks()
  const { data: drops } = useMyDrops()

  const solved = useMemo(() => new Map((drops ?? []).map((d) => [d.task.id, d])), [drops])

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Инбокс задач
        </span>
        <h1 className="text-2xl font-bold">Микрозадачи</h1>
        <p className="text-sm text-muted-foreground">
          Решите задачу — решение подтверждает навык и может привести к офферу. Отметка «задача»
          у скилла приходит из найма по этой задаче.
        </p>
      </header>

      {isLoading ? (
        <RowSkeleton count={4} />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : tasks && tasks.length > 0 ? (
        <div className="flex flex-col gap-3">
          {tasks.map((task) => (
            <MicrotaskCard key={task.id} task={task} drop={solved.get(task.id) ?? null} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Задач пока нет"
          description="Когда компания опубликует микрозадачу, она появится здесь."
        />
      )}
    </section>
  )
}

function MicrotaskCard({ task, drop }: { task: MicroTask; drop: MicroTaskDrop | null }) {
  const done = Boolean(drop)
  const score = drop?.score ?? null
  const reviewed = done && score !== null

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{task.company.name}</span>
            <TrustBadge level={task.company.trust_level} />
            <span>· {SPEC_LABEL[task.specialization]}</span>
          </div>
          <h3 className="text-base font-semibold">{task.title}</h3>
        </div>
        <span className="rounded-md border border-border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
          {MICROTASK_FORMAT_LABEL[task.format]}
        </span>
      </div>

      <p className="line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{task.prompt_md}</p>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock3 className="h-3.5 w-3.5" />
          до {new Date(task.deadline).toLocaleDateString('ru-RU')}
          {task.grades.length > 0 && (
            <span className="text-muted-foreground"> · {task.grades.map((g) => GRADE_LABEL[g]).join(', ')}</span>
          )}
        </span>

        {done ? (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-plus">
            <CheckCircle2 className="h-4 w-4" />
            {reviewed ? `Решено, оценка ${score}/5` : 'Решено, ждём ревью'}
          </span>
        ) : (
          <Button size="sm" asChild>
            <Link to={`/candidate/microtasks/${task.id}`}>
              Решить <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        )}
      </div>
    </article>
  )
}