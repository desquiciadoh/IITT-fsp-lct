import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ChevronRight, Send, Timer } from 'lucide-react'
import { useFinishAssessment, usePostAnswer, useSession } from '@/api/assessments'
import { ApiError } from '@/api/client'
import type { AssessmentItem, AssessmentSession, AnswerInput } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ErrorState } from '@/components/domain/states'
import { CardSkeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/i18n/errors'
import { useCountdown } from '@/lib/hooks/useCountdown'
import { MarkdownText, CodeBlock } from './render'
import { useIntegrity, toWireIntegrity } from './integrity'

/**
 * FE-05 · Test runner (`/candidate/qualification/:id`).
 *
 * One screen per served item. State comes exclusively from the session query
 * (cache primed by `useCreateAssessment`, kept fresh in place by
 * `usePostAnswer`), so a refresh mid-test resumes through GET with no extra
 * wiring (stateful MSW mock keeps the cursor server-side).
 *
 * Timing: the deadline is authoritative on the server; the client corrects
 * clock skew by anchoring `deadline_at`/`served_at` to the local receive
 * moment (see `skewAdjustedDeadline`) and auto-submits whatever answer is
 * selected when the countdown hits zero (empty counts as incorrect — BE.md H5).
 *
 * Integrity: focus-loss / paste counters are captured silently per item and
 * sent with the answer; nothing about them is shown to the candidate.
 */

// --- pure helpers (unit-tested in test-runner-page.test.ts) ---------------------

/**
 * Anchor a server deadline to the local clock:
 *   remaining = (deadline_at − served_at) − elapsed_local_since_receive
 * i.e. we trust the *duration* from the payload and our own monotonic-ish
 * wall clock at receive time, not the absolute server timestamp. A wrong
 * device clock therefore cannot shorten/lengthen the real budget.
 * Falls back to the raw deadline when timestamps are missing/unparseable.
 */
export function skewAdjustedDeadline(item: AssessmentItem, receivedAtMs: number): string {
  const served = item.served_at ? Date.parse(item.served_at) : NaN
  const deadline = item.deadline_at ? Date.parse(item.deadline_at) : NaN
  if (Number.isNaN(served) || Number.isNaN(deadline) || receivedAtMs <= 0) {
    return item.deadline_at ?? ''
  }
  const durationMs = Math.max(0, deadline - served)
  return new Date(receivedAtMs + durationMs).toISOString()
}

/** Build the POST body for one item from the draft answer + integrity counters. */
export function buildAnswerInput(
  item: AssessmentItem,
  choice: string | null,
  textValue: string,
  integrity: AnswerInput['integrity'],
): AnswerInput {
  if (item.input_type === 'choice') {
    return { item_id: item.item_id, option_id: choice ?? '', integrity }
  }
  return { item_id: item.item_id, value: textValue.trim(), integrity }
}

/** Where to go once the last answer lands (FE-06 owns that screen). */
export function resultPath(id: string): string {
  return `/candidate/qualification/${id}/result`
}

// --- component -------------------------------------------------------------------

/** Terminal state after a manual early finish (FE-06 owns the result screen). */
function FinishedNotice({ id }: { id: string }) {
  const navigate = useNavigate()
  return (
    <Card aria-label="Тест завершён">
      <CardHeader>
        <CardTitle className="text-base">Тест завершен</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Ответы сохранены, попытка засчитана. Перейдите к результатам, чтобы увидеть оценку.
        </p>
        <Button onClick={() => navigate(resultPath(id), { replace: true })}>
          К результатам
          <ChevronRight className="ml-2 h-4 w-4" aria-hidden />
        </Button>
      </CardContent>
    </Card>
  )
}

export function TestRunnerPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const sessionQuery = useSession(id)

  // Local wall-clock at the moment this item's payload was (re)received —
  // recorded once per item via ref so re-renders don't drift the anchor.
  const receivedAtRef = useRef<Map<string, number>>(new Map())
  const item = sessionQuery.data?.current ?? null
  if (item && !receivedAtRef.current.has(item.item_id)) {
    receivedAtRef.current.set(item.item_id, Date.now())
  }

  return <RunnerBody id={id} item={item} session={sessionQuery.data} receivedAtMs={item ? (receivedAtRef.current.get(item.item_id) ?? 0) : 0} query={sessionQuery} navigate={navigate} />
}

function RunnerBody({
  id,
  item,
  session,
  receivedAtMs,
  query,
  navigate,
}: {
  id: string
  item: AssessmentItem | null
  session?: AssessmentSession
  receivedAtMs: number
  query: ReturnType<typeof useSession>
  navigate: (to: string, opts?: { replace?: boolean }) => void
}) {
  const [choice, setChoice] = useState<string | null>(null)
  const [textValue, setTextValue] = useState('')
  const [finishOpen, setFinishOpen] = useState(false)
  const [finished, setFinished] = useState(false)
  const answer = usePostAnswer(id)
  const finish = useFinishAssessment(id)
  const { read, bumpPaste } = useIntegrity(item?.item_id)

  // Draft resets on every new item.
  useEffect(() => {
    setChoice(null)
    setTextValue('')
  }, [item?.item_id])

  const adjustedDeadline = useMemo(
    () => (item ? skewAdjustedDeadline(item, receivedAtMs) : null),
    [item, receivedAtMs],
  )
  const { remainingMs, expired } = useCountdown(adjustedDeadline)

  // Latest submit closure, so effects can call it without listing the whole
  // mutable context in their dependency arrays.
  const submitRef = useRef<(auto?: boolean) => void>(() => {})

  const submit = (auto: boolean) => {
    if (!item || answer.isPending) return
    answer.mutate(buildAnswerInput(item, choice, textValue, toWireIntegrity(read())), {
      onSuccess: (outcome) => {
        if (outcome.done) {
          navigate(resultPath(id), { replace: true })
        }
        // else: cache updated in place → next item renders; counters reset.
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError && err.code === 'item_not_current') {
          // Another tab answered already — pull the authoritative session.
          void query.refetch()
          return
        }
        if (err instanceof ApiError && err.code === 'assessment_expired') {
          toast.error(errorMessage('assessment_expired'))
          navigate(resultPath(id), { replace: true })
          return
        }
        toast.error(err instanceof ApiError ? errorMessage(err.code) : 'Не удалось отправить ответ.')
        if (!auto) return
        // Auto-submit failed → retry once shortly; never trap the candidate.
        window.setTimeout(() => submit(true), 2000)
      },
    })
  }

  // Keep the ref pointing at the freshest closure (item, draft, integrity).
  useEffect(() => {
    submitRef.current = () => submit(true)
  })

  // Expiration → fire exactly one auto-submit per item.
  const autoFiredFor = useRef<string | null>(null)
  useEffect(() => {
    if (!expired || !item) return
    if (autoFiredFor.current === item.item_id) return
    autoFiredFor.current = item.item_id
    submitRef.current(true)
  }, [expired, item])

  // Browser "back" must not leave the test mid-item: while an item is live we
  // keep a sentinel history entry and bounce back if the candidate pops it.
  const hasItem = Boolean(item)
  useEffect(() => {
    if (!hasItem) return
    const onPop = () => {
      // Re-push the sentinel and stay on the runner.
      window.history.pushState({ qaGuard: true }, '')
    }
    window.history.pushState({ qaGuard: true }, '')
    window.addEventListener('popstate', onPop)
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('beforeunload', warn)
    }
  }, [hasItem])

  /**
   * Confirmed early finish: POST /api/assessments/{id}/finish (G5 shipped on
   * the BE; stateful mock in qualification.ts for `all` mode).
   * The draft answer for the unsent current item is intentionally dropped —
   * the backend treats the unanswered tail as incorrect; <50% answered →
   * `not_enough_answers` (attempt abandoned, BE.md R9) — we still hand off
   * to the result route so FE-06 can explain what happened.
   */
  const confirmFinish = () => {
    finish.mutate(undefined, {
      onSuccess: () => {
        setFinishOpen(false)
        setFinished(true)
      },
      onError: (err: unknown) => {
        toast.error(err instanceof ApiError ? errorMessage(err.code) : 'Не удалось завершить тест.')
        if (err instanceof ApiError && err.code === 'invalid_transition') {
          // Finished elsewhere (e.g. the last answer landed in another tab).
          setFinishOpen(false)
          void query.refetch()
        }
      },
    })
  }

  // --- render states -------------------------------------------------------------

  // Manual early finish landed → terminal notice instead of the item card.
  // Rendered here (not via an early return above) so every hook runs on
  // every render in a stable order (react-hooks/rules-of-hooks).
  if (finished) return <FinishedNotice id={id} />

  if (query.isLoading) return <CardSkeleton />

  if (query.isError) {
    const code = query.error instanceof ApiError ? query.error.code : undefined
    if (code === 'not_found') {
      return (
        <ErrorState
          title="Сессия теста не найдена"
          description="Возможно, она уже завершена. Начните новую попытку со стартового экрана."
          code={code}
          onRetry={() => navigate('/candidate/qualification/start', { replace: true })}
        />
      )
    }
    return (
      <ErrorState
        title="Не удалось загрузить тест"
        description="Прогресс сохранён на сервере — повторите загрузку."
        code={code}
        onRetry={() => void query.refetch()}
      />
    )
  }

  // No current item but the session exists: finished elsewhere/expired → results.
  if (!item) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Текущее задание недоступно</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Сессия уже завершена или истекло общее время теста. Перейдите к результатам.
          </p>
          <Button onClick={() => navigate(resultPath(id), { replace: true })}>
            К результатам
            <ChevronRight className="ml-2 h-4 w-4" aria-hidden />
          </Button>
        </CardContent>
      </Card>
    )
  }

  const secondsLeft = Math.ceil(remainingMs / 1000)
  const total = session?.max_items ?? null
  const canSubmit = item.input_type === 'choice' ? Boolean(choice) : textValue.trim().length > 0

  return (
    <Card aria-label="Задание теста">
      <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="text-base">
            Задание {item.seq}
            {total ? ` из ${total}` : ''}
          </CardTitle>
          {typeof item.level === 'number' && (
            <p className="text-xs text-muted-foreground">Сложность: {item.level}</p>
          )}
        </div>
        {/* Server-authoritative timer, skew-corrected client-side. */}
        <div
          className="flex items-center gap-1.5 rounded-md border bg-muted/40 px-3 py-1.5 font-mono text-sm tabular-nums"
          role="timer"
          aria-label={`Осталось ${secondsLeft} секунд`}
          data-expiring={secondsLeft <= 10 ? 'true' : undefined}
        >
          <Timer className="h-4 w-4 text-muted-foreground" aria-hidden />
          {String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:
          {String(secondsLeft % 60).padStart(2, '0')}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <MarkdownText text={item.stem_md} className="text-sm leading-relaxed" />

        {item.code && <CodeBlock code={item.code.text} lang={item.code.lang} />}

        {item.input_type === 'choice' && (
          <fieldset className="space-y-2" onPaste={bumpPaste}>
            <legend className="sr-only">Варианты ответа</legend>
            {(item.options ?? []).map((opt) => (
              <label
                key={opt.id}
                className="flex cursor-pointer items-start gap-3 rounded-md border px-4 py-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
              >
                <input
                  type="radio"
                  name={`item-${item.item_id}`}
                  value={opt.id}
                  checked={choice === opt.id}
                  onChange={() => setChoice(opt.id)}
                  disabled={answer.isPending}
                  className="mt-0.5"
                />
                <MarkdownText text={opt.text_md} className="min-w-0 flex-1" />
              </label>
            ))}
          </fieldset>
        )}

        {item.input_type === 'number' && (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Ответ (число)</span>
            <Input
              type="number"
              inputMode="numeric"
              value={textValue}
              onChange={(e) => setTextValue(e.target.value)}
              onPaste={bumpPaste}
              disabled={answer.isPending}
              autoFocus
            />
          </label>
        )}

        {item.input_type === 'text' && (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Ответ</span>
            <textarea
              className="min-h-24 w-full rounded-md border bg-transparent p-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={textValue}
              onChange={(e) => setTextValue(e.target.value)}
              onPaste={bumpPaste}
              disabled={answer.isPending}
              autoFocus
            />
          </label>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {answer.isPending
              ? 'Отправляем…'
              : canSubmit
                ? 'Ответ будет засчитан сразу после отправки.'
                : 'Выберите ответ, чтобы продолжить.'}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setFinishOpen(true)} disabled={finish.isPending}>
              Завершить досрочно
            </Button>
            <Button onClick={() => submit(false)} disabled={!canSubmit || answer.isPending}>
              Следующее задание
              <Send className="ml-2 h-4 w-4" aria-hidden />
            </Button>
          </div>
        </div>
      </CardContent>

      {/* Early-finish confirmation. Neutral UX: no warnings about integrity. */}
      <Dialog open={finishOpen} onOpenChange={(o) => !o && !finish.isPending && setFinishOpen(false)}>
        <DialogContent showCloseButton={!finish.isPending}>
          <DialogHeader>
            <DialogTitle>Завершить тест досрочно?</DialogTitle>
            <DialogDescription>
              Вы уверены? Прогресс будет сохранен: уже отправленные ответы засчитаются, текущее
              задание без ответа останется незавершённым. Изменить ответы после завершения нельзя.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFinishOpen(false)} disabled={finish.isPending}>
              Отмена
            </Button>
            <Button onClick={confirmFinish} disabled={finish.isPending}>
              {finish.isPending ? 'Завершаем…' : 'Да, завершить'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
