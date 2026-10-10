import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { PlayCircle, RotateCcw, Timer } from 'lucide-react'
import { useEligibility, useCreateAssessment } from '@/api/assessments'
import { ApiError } from '@/api/client'
import type { AssessmentKind, AssessmentMode, Grade, Spec } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState } from '@/components/domain/states'
import { CardSkeleton } from '@/components/ui/skeleton'

/**
 * FE-05 · Test runner — start screen (`/candidate/qualification/start`).
 *
 * State machine driven by GET /api/assessments/eligibility (stateful MSW mock
 * in `all` mode, see src/mocks/handlers/qualification.ts):
 *  - loading            → skeleton
 *  - active_session_id  → "Продолжить тест" (resume via the runner route)
 *  - cooldown_active    → live countdown to next_attempt_at, form hidden
 *  - can_start          → Full/Express form → POST /api/assessments → runner
 *
 * The claimed grade defines the cut for the `decision` (FE2.md §FE-05), so it
 * stays editable here even though the profile already carries one.
 */

// --- form config -----------------------------------------------------------------

const SPEC_OPTIONS: { value: Spec; label: string }[] = [
  { value: 'backend', label: 'Бэкенд' },
  { value: 'frontend', label: 'Фронтенд' },
  { value: 'ml_data', label: 'ML и данные' },
]

const GRADE_OPTIONS: { value: Grade; label: string }[] = [
  { value: 'intern', label: 'Интерн' },
  { value: 'junior', label: 'Джуниор' },
  { value: 'middle', label: 'Мидл' },
  { value: 'senior', label: 'Сеньор' },
]

const MODE_OPTIONS: { value: AssessmentMode; label: string; hint: string }[] = [
  { value: 'full', label: 'Полный', hint: '~12 заданий · точнее оценка' },
  { value: 'express', label: 'Экспресс', hint: '~6 заданий · быстрый срез' },
]

const startFormSchema = z.object({
  specialization: z.enum(['backend', 'frontend', 'ml_data']),
  claimed_grade: z.enum(['intern', 'junior', 'middle', 'senior']),
  mode: z.enum(['full', 'express']),
})

type StartFormValues = z.infer<typeof startFormSchema>

// --- pure helpers (unit-tested in start-page.test.ts) -----------------------------

/** Test rules shown on the start screen (FE2.md §FE-05: "read the rules"). */
export const TEST_RULES: string[] = [
  'Отвечайте на задания по порядку — у каждого задания собственный таймер.',
  'Ответ, отправленный позже чем через 3 секунды после истечения таймера, не засчитывается.',
  'Можно завершить тест досрочно; без ответа оставшиеся задания засчитываются как неверные.',
  'Обновление страницы не сбрасывает прогресс — тест продолжится с текущего задания.',
  'После засчитанной попытки следующая станет доступна через 48 часов.',
]

/** Which kind of session the start button creates (promotion test when the
 *  candidate is eligible for one — FE2.md §FE-05 eligibility payload). */
export function assessmentKindFor(eligibility: EligibilityLike | undefined): AssessmentKind {
  return eligibility?.promotion_available ? 'promotion' : 'initial'
}

export type CountdownParts = { done: boolean; hours: number; minutes: number; seconds: number }

/** Whole seconds remaining until `isoAt`, evaluated against `nowMs`. */
export function countdownTo(isoAt: string | null | undefined, nowMs: number): CountdownParts {
  if (!isoAt) return { done: true, hours: 0, minutes: 0, seconds: 0 }
  const ms = new Date(isoAt).getTime() - nowMs
  if (Number.isNaN(ms) || ms <= 0) return { done: true, hours: 0, minutes: 0, seconds: 0 }
  const total = Math.ceil(ms / 1000)
  return {
    done: false,
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  }
}

export function formatCountdown(p: CountdownParts): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return p.hours > 0
    ? `${p.hours} ч ${pad(p.minutes)} мин ${pad(p.seconds)} с`
    : `${pad(p.minutes)}:${pad(p.seconds)}`
}

/** Which screen the eligibility response selects. */
export type StartViewState = 'loading' | 'error' | 'resume' | 'cooldown' | 'form'

/** Minimal shape `resolveStartView` needs — keeps it unit-testable in node env. */
export type EligibilityLike = {
  can_start: boolean
  promotion_available?: boolean
  reason?: string
  active_session_id?: string | null
  next_attempt_at?: string | null
}

export function resolveStartView(
  eligibility: EligibilityLike | undefined,
  isLoading: boolean,
  isError: boolean,
): StartViewState {
  if (isLoading) return 'loading'
  if (isError || !eligibility) return 'error'
  if (eligibility.active_session_id) return 'resume'
  if (!eligibility.can_start && eligibility.reason === 'cooldown_active') return 'cooldown'
  if (!eligibility.can_start) return 'error' // unknown block reason → fail closed
  return 'form'
}

// --- component ---------------------------------------------------------------------

/** FE-05 start screen. */
export function StartPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // FE2.md §FE-05: read `specialization` and `claimed_grade` from the query
  // string — FE1's onboarding deep-links here with these params prefilled.
  const qsSpec = (SPEC_OPTIONS.find((o) => o.value === searchParams.get('specialization'))?.value ??
    'backend') as Spec
  const qsGrade = GRADE_OPTIONS.some((o) => o.value === searchParams.get('claimed_grade'))
    ? (searchParams.get('claimed_grade') as Grade)
    : 'junior'

  const [spec, setSpec] = useState<Spec>(qsSpec)
  const eligibility = useEligibility(spec)
  const view = resolveStartView(eligibility.data, eligibility.isLoading, eligibility.isError)

  const form = useForm<StartFormValues>({
    resolver: zodResolver(startFormSchema),
    defaultValues: { specialization: qsSpec, claimed_grade: qsGrade, mode: 'full' },
  })

  // The eligibility query follows the specialization chosen in the form.
  const formSpec = form.watch('specialization')
  useEffect(() => {
    if (formSpec !== spec) setSpec(formSpec)
  }, [formSpec, spec])

  const createAssessment = useCreateAssessment()

  // Cooldown ticker: re-render once per second while counting down.
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (view !== 'cooldown') return
    const id = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [view])

  const cd = useMemo(
    () => countdownTo(eligibility.data?.next_attempt_at, nowMs),
    [eligibility.data?.next_attempt_at, nowMs],
  )

  // Refetch eligibility as soon as the cooldown expires (button unlocks itself).
  useEffect(() => {
    if (view === 'cooldown' && cd.done) void eligibility.refetch()
  }, [view, cd.done, eligibility])

  const onStart = form.handleSubmit((values) => {
    createAssessment.mutate(
      { ...values, kind: assessmentKindFor(eligibility.data) },
      {
        onSuccess: (session) => navigate(`/candidate/qualification/${session.id}`),
        onError: (err: unknown) => {
          if (err instanceof ApiError && err.code === 'assessment_in_progress') {
            // Race with another tab / stale eligibility → show resume instead.
            void eligibility.refetch()
          }
          toast.error(
            err instanceof ApiError ? err.message : 'Не удалось начать тест. Попробуйте ещё раз.',
          )
        },
      },
    )
  })

  if (view === 'loading') return <CardSkeleton />

  if (view === 'error') {
    return (
      <ErrorState
        title="Не удалось проверить доступ к тесту"
        description="Проверьте соединение и обновите страницу."
        onRetry={() => void eligibility.refetch()}
      />
    )
  }

  if (view === 'resume') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>У вас незавершённый тест</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Вы прервали прохождение ранее. Прогресс сохранён — можно продолжить с текущего задания.
          </p>
          <Button
            onClick={() =>
              navigate(`/candidate/qualification/${eligibility.data?.active_session_id}`)
            }
          >
            <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
            Продолжить тест
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (view === 'cooldown') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Пауза между попытками</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            После засчитанной попытки действует перерыв 48 часа. Следующая попытка станет доступна,
            когда таймер дойдёт до нуля.
          </p>
          <div
            className="flex items-center gap-2 rounded-md border bg-muted/40 px-4 py-3 font-mono text-lg tabular-nums"
            role="timer"
            aria-label="До следующей попытки"
          >
            <Timer className="h-5 w-5 text-muted-foreground" aria-hidden />
            {formatCountdown(cd)}
          </div>
        </CardContent>
      </Card>
    )
  }

  // view === 'form'
  const promotionAvailable = Boolean(eligibility.data?.promotion_available)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{promotionAvailable ? 'Промо-тест на повышение' : 'Квалификационный тест'}</CardTitle>
      </CardHeader>
      <CardContent>
        {promotionAvailable && (
          <p className="mb-4 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm text-muted-foreground">
            Вам доступна попытка на повышение — подтвердите более высокую ступень.
          </p>
        )}
        <form className="space-y-6" onSubmit={onStart} aria-label="Запуск квалификационного теста">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Специализация</legend>
            <select
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              {...form.register('specialization')}
              aria-label="Специализация"
            >
              {SPEC_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Заявляемая ступень</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {GRADE_OPTIONS.map((o) => (
                <label
                  key={o.value}
                  className="flex cursor-pointer items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm has-[:checked]:border-primary has-[:checked]:font-medium"
                >
                  <input
                    type="radio"
                    value={o.value}
                    {...form.register('claimed_grade')}
                    className="sr-only"
                  />
                  {o.label}
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Результат теста подтвердит или скорректирует эту ступень в профиле.
            </p>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Режим прохождения</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {MODE_OPTIONS.map((o) => (
                <label
                  key={o.value}
                  className="flex cursor-pointer flex-col gap-1 rounded-md border px-4 py-3 text-sm has-[:checked]:border-primary"
                >
                  <span className="flex items-center gap-2 font-medium">
                    <input
                      type="radio"
                      value={o.value}
                      {...form.register('mode')}
                      className="sr-only"
                    />
                    {o.label}
                  </span>
                  <span className="text-xs text-muted-foreground">{o.hint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Правила теста</legend>
            <ul className="list-disc space-y-1 rounded-md border bg-muted/30 px-8 py-3 text-xs text-muted-foreground">
              {TEST_RULES.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </fieldset>

          <Button type="submit" disabled={createAssessment.isPending}>
            <PlayCircle className="mr-2 h-4 w-4" aria-hidden />
            {createAssessment.isPending ? 'Запускаем тест…' : 'Начать тест'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
