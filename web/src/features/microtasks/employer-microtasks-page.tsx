import { useState } from 'react'
import { ClipboardList, FilePlus2, Send, Star } from 'lucide-react'
import { toast } from 'sonner'
import {
  useCreateMicroTask,
  useEmployerMicroTasks,
  useReviewDrop,
} from '@/api/microtasks'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useCreateOffer } from '@/api/offers'
import { Button } from '@/components/ui/button'
import { RowSkeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/domain/states'
import { GRADE_LABEL, MICROTASK_FORMAT_LABEL, SPEC_LABEL } from '@/lib/labels'
import type { MicroTaskDrop } from '@/api/types'

const SPEC_OPTIONS = Object.entries(SPEC_LABEL).map(([value, label]) => ({ value, label }))
const GRADE_OPTIONS = Object.entries(GRADE_LABEL).map(([value, label]) => ({ value, label }))

/**
 * FE-16 employer part: create a micro-task, review open submissions, then
 * invite a candidate from a shared submission with a Draft offer. Previewed at
 * `/dev/microtasks-employer` until FE2's position pages land (FE-09/FE-10).
 */
export function EmployerMicrotasksPage() {
  const { data: tasks, isLoading, isError, refetch } = useEmployerMicroTasks()

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Работодатель · микрозадачи
        </span>
        <h1 className="text-2xl font-bold">Задачи и решения</h1>
        <p className="text-sm text-muted-foreground">
          Публикуйте задачи, проверяйте свободные ответы и приглашайте в отклик из просмотренного
          решения — решение становится evidence «задача».
        </p>
      </header>

      <CreateTaskForm />

      {isLoading ? (
        <RowSkeleton count={4} />
      ) : isError ? (
        <p className="text-sm text-destructive">
          Не удалось загрузить задачи.{' '}
          <button className="underline underline-offset-4" onClick={() => void refetch()}>
            Повторить
          </button>
        </p>
      ) : tasks && tasks.length > 0 ? (
        <div className="flex flex-col gap-4">
          {tasks.map((task) => (
            <TaskSubmissions key={task.id} taskId={task.id} />
          ))}
        </div>
      ) : (
        <EmptyState title="Задач пока нет" description="Создайте первую задачу формой выше." />
      )}
    </section>
  )
}

function CreateTaskForm() {
  const create = useCreateMicroTask()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [specialization, setSpecialization] = useState('backend')
  const [grade, setGrade] = useState('middle')
  const [format, setFormat] = useState<'auto' | 'open'>('auto')
  const [prompt, setPrompt] = useState('')

  if (!open)
    return (
      <Button variant="outline" className="self-start" onClick={() => setOpen(true)}>
        <FilePlus2 className="h-4 w-4" /> Новая задача
      </Button>
    )

  return (
    <form
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          {
            title,
            specialization,
            grades: [grade],
            format,
            prompt_md: prompt,
            deadline: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(),
          },
          {
            onSuccess: () => {
              toast.success('Задача опубликована')
              setOpen(false)
              setTitle('')
              setPrompt('')
            },
            onError: (error) =>
              toast.error(
                error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось создать задачу.',
              ),
          },
        )
      }}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
          Название
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm normal-case text-foreground outline-none focus:border-primary"
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Специализация
            <select
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
              className="rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-primary"
            >
              {SPEC_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Грейд
            <select
              value={grade}
              onChange={(e) => setGrade(e.target.value)}
              className="rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-primary"
            >
              {GRADE_OPTIONS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground">
        Формат проверки
        {(['auto', 'open'] as const).map((f) => (
          <label
            key={f}
            className="ml-3 inline-flex cursor-pointer items-center gap-1.5 text-sm normal-case text-foreground"
          >
            <input
              type="radio"
              name="microtask-format"
              checked={format === f}
              onChange={() => setFormat(f)}
            />
            {MICROTASK_FORMAT_LABEL[f]}
          </label>
        ))}
      </div>

      <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
        Условие задачи (Markdown)
        <textarea
          rows={5}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm normal-case text-foreground outline-none focus:border-primary"
        />
      </label>

      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          <ClipboardList className="h-4 w-4" /> Опубликовать
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={create.isPending}>
          Отмена
        </Button>
      </div>
    </form>
  )
}

function TaskSubmissions({ taskId }: { taskId: string }) {
  const { data: tasks } = useEmployerMicroTasks()
  const task = tasks?.find((t) => t.id === taskId)
  if (!task) return null

  return (
    <details className="group flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-base font-semibold">{task.title}</span>
          <span className="text-xs text-muted-foreground">
            {SPEC_LABEL[task.specialization]} · {task.grades.map((g) => GRADE_LABEL[g]).join(', ')} ·{' '}
            {MICROTASK_FORMAT_LABEL[task.format]} · решений:{' '}
            {task.submissions.length}
          </span>
        </div>
        <span className="text-sm text-muted-foreground">развернуть ▼</span>
      </summary>

      {task.submissions.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-3 border-t border-border pt-3">
          {task.submissions.map((drop) => (
            <SubmissionRow key={drop.id} drop={drop} />
          ))}
        </ul>
      ) : (
        <p className="mt-3 border-t border-border pt-3 text-sm text-muted-foreground">
          Решений пока нет.
        </p>
      )}
    </details>
  )
}

function SubmissionRow({ drop }: { drop: MicroTaskDrop }) {
  const review = useReviewDrop()
  const sendOffer = useCreateOffer()
  const [rating, setRating] = useState(drop.employer_rating ?? 5)
  const [shared, setShared] = useState(drop.shared)
  const [inviting, setInviting] = useState(false)
  const [offer, setOffer] = useState({
    title: `Оффер по итогам микрозадачи · ${drop.task.title}`,
    salary_min: 200000,
    salary_max: 300000,
    contact_channel: 'platform',
    contact_value: '',
  })

  const needsReview = drop.employer_rating === null && drop.task.format === 'open'
  const handleError = (error: unknown) =>
    toast.error(error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось выполнить запрос.')

  const saveReview = () =>
    review.mutate(
      { id: drop.id, rating, shared },
      {
        onSuccess: () => toast.success('Решение отмечено и сохранено как evidence'),
        onError: handleError,
      },
    )

  const submitOffer = () =>
    sendOffer.mutate(
      {
        candidate_public_id: drop.candidate.public_id,
        title: offer.title,
        description: `Приглашение по результатам микрозадачи «${drop.task.title}».`,
        salary_min: offer.salary_min,
        salary_max: offer.salary_max,
        salary_type: 'gross',
        contact_channel: offer.contact_channel as 'platform' | 'email' | 'telegram',
        contact_value: offer.contact_value,
      },
      {
        onSuccess: () => {
          toast.success('Draft оффер создан и отправлен кандидату')
          setInviting(false)
        },
        onError: handleError,
      },
    )

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-mono text-xs">
          {drop.candidate.display_name} · {drop.candidate.public_id}
        </span>
        {drop.employer_rating !== null ? (
          <span className="inline-flex items-center gap-1 rounded-md border border-info/40 bg-info/10 px-2 py-0.5 text-xs text-info">
            <Star className="h-3 w-3 fill-current" /> {drop.employer_rating}/5 · evidence «задача»
          </span>
        ) : (
          <span className="rounded-md border border-border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
            ждёт ревью
          </span>
        )}
      </div>

      <pre className="whitespace-pre-wrap rounded-md bg-muted px-3 py-2 font-sans text-sm text-muted-foreground">
        {String(drop.answer)}
      </pre>

      {needsReview ? (
        <div className="flex flex-wrap items-end gap-3 rounded-md border border-border p-3">
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Оценка
            <select
              value={rating}
              onChange={(e) => setRating(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="inline-flex cursor-pointer items-center gap-2 pb-2 text-sm text-foreground">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            Показывать кандидату как evidence
          </label>
          <Button size="sm" onClick={saveReview} disabled={review.isPending}>
            Сохранить ревью
          </Button>
        </div>
      ) : (
        drop.shared && (
          <div className="flex flex-col gap-3">
            <Button variant="outline" size="sm" className="self-start" onClick={() => setInviting((v) => !v)}>
              <Send className="h-4 w-4" /> {inviting ? 'Скрыть форму' : 'Пригласить на оффер'}
            </Button>
            {inviting && (
              <div className="flex flex-col gap-3 rounded-md border border-border p-3">
                <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Название оффера
                  <input
                    value={offer.title}
                    onChange={(e) => setOffer({ ...offer, title: e.target.value })}
                    className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                  />
                </label>
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                    Зарплата от
                    <input
                      type="number"
                      value={offer.salary_min}
                      onChange={(e) => setOffer({ ...offer, salary_min: Number(e.target.value) })}
                      className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                    Зарплата до
                    <input
                      type="number"
                      value={offer.salary_max}
                      onChange={(e) => setOffer({ ...offer, salary_max: Number(e.target.value) })}
                      className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                    Канал связи
                    <select
                      value={offer.contact_channel}
                      onChange={(e) => setOffer({ ...offer, contact_channel: e.target.value })}
                      className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                    >
                      <option value="platform">Платформа</option>
                      <option value="email">Email</option>
                      <option value="telegram">Telegram</option>
                    </select>
                  </label>
                </div>
                <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Контакт (если выбран не «платформа»)
                  <input
                    value={offer.contact_value}
                    onChange={(e) => setOffer({ ...offer, contact_value: e.target.value })}
                    placeholder="@username или email"
                    className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                  />
                </label>
                <Button size="sm" className="self-start" onClick={submitOffer} disabled={sendOffer.isPending}>
                  <Send className="h-4 w-4" /> Отправить draft-оффер
                </Button>
              </div>
            )}
          </div>
        )
      )}
    </li>
  )
}