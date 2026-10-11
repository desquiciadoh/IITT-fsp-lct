import { useParams, Link } from 'react-router-dom'
import { useState } from 'react'
import { Download, Flag, Rocket, Timer } from 'lucide-react'
import { toast } from 'sonner'
import {
  useResult,
  useHistory,
  useEligibility,
  downloadPlayerCard,
} from '@/api/assessments'
import { useProfile } from '@/api/profile'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { cn } from '@/lib/utils'
import { useCountdown } from '@/lib/hooks/useCountdown'
import { formatDate, formatDuration } from '@/lib/format'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'
import { RatingBadge } from '@/components/domain/rating-badge'
import { ErrorState, EmptyState } from '@/components/domain/states'
import { CardSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import type { AssessmentResult } from '@/api/types'

const DECISION_COPY = {
  confirmed: {
    title: 'Грейд подтверждён',
    note: 'Результат валиден: вы в лиге с этим грейдом, карточка обновлена.',
    tone: 'text-[var(--fsp-league-confirmed)]',
  },
  unconfirmed: {
    title: 'Грейд заявлен, не подтверждён',
    note: 'Профиль остаётся видимым работодателям, но в рейтинге вы ранжируетесь ниже.',
    tone: 'text-[var(--fsp-league-unconfirmed)]',
  },
} as const

function Cooldown({ deadline }: { deadline: string }) {
  const { remainingMs, expired } = useCountdown(deadline)
  if (expired) return null
  return (
    <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <Timer className="h-4 w-4" />
      Повторная попытка через {formatDuration(remainingMs)}
    </span>
  )
}

const TOPIC_LABEL_MAP: Record<string, string> = {
  architecture: 'Архитектура',
  performance: 'Производительность',
  testing: 'Тестирование',
  security: 'Безопасность',
  product_thinking: 'Продуктовое мышление',
  mentoring: 'Менторство',
  general: 'Общие темы',
  python: 'Python',
  sql: 'SQL',
  javascript: 'JavaScript',
}

const LEVEL_LABEL_MAP: Record<string, string> = {
  strong: 'уверенно',
  moderate: 'средне',
  limited: 'базово',
}

function TopicsChart({ topics }: { topics: NonNullable<AssessmentResult['topics']> }) {
  return (
    <div className="flex flex-col gap-2.5">
      <h3 className="text-sm font-semibold">Темы</h3>
      {topics.map((topic, idx) => {
        const key = topic.key ?? topic.topic ?? `topic-${idx}`
        const label =
          topic.label ??
          TOPIC_LABEL_MAP[topic.topic ?? ''] ??
          topic.topic ??
          topic.key ??
          `Тема ${idx + 1}`
        const hasCounts = topic.total != null && topic.correct != null
        const pct = hasCounts
          ? topic.total! > 0
            ? Math.round((topic.correct! / topic.total!) * 100)
            : 0
          : topic.level === 'strong'
            ? 100
            : topic.level === 'moderate'
              ? 60
              : 30
        const statText = hasCounts
          ? `${topic.correct}/${topic.total}`
          : LEVEL_LABEL_MAP[topic.level ?? ''] ?? topic.level ?? ''

        return (
          <div key={key} className="flex items-center gap-3">
            <span className="w-40 shrink-0 truncate text-xs text-muted-foreground" title={label}>
              {label}
            </span>
            <div
              className="h-3 flex-1 overflow-hidden rounded-full bg-secondary"
              role="img"
              aria-label={`${label}: ${statText}`}
            >
              <div
                className={cn(
                  'h-full rounded-full',
                  pct >= 75 ? 'bg-[var(--fsp-league-confirmed)]' : pct >= 50 ? 'bg-warn' : 'bg-destructive',
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
              {statText}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function EvidenceChart({ evidence }: { evidence: NonNullable<AssessmentResult['evidence']> }) {
  return (
    <div className="flex flex-col gap-2.5">
      <h3 className="text-sm font-semibold">Задания: уровень × верно</h3>
      <div className="flex flex-wrap gap-1.5">
        {evidence.map((point) => (
          <span
            key={point.seq}
            title={`Задание ${point.seq}: ${
              point.correct === null ? 'нет данных' : point.correct ? 'верно' : 'неверно'
            }`}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded text-[11px] font-semibold tabular-nums',
              point.correct === null
                ? 'bg-secondary text-muted-foreground'
                : point.correct
                  ? 'bg-[var(--fsp-league-confirmed)]/15 text-[var(--fsp-league-confirmed)]'
                  : 'bg-destructive/15 text-destructive',
            )}
          >
            {point.seq}
          </span>
        ))}
      </div>
      <div className="flex gap-3 text-[11px] text-muted-foreground">
        <span>зелёный — верно</span>
        <span>красный — неверно</span>
        <span>серый — без ответа</span>
      </div>
    </div>
  )
}

function HistoryList({ currentId }: { currentId: string }) {
  const { data, isLoading, isError } = useHistory()
  if (isLoading) return <CardSkeleton />
  if (isError || !data) return null
  if (data.length === 0) {
    return (
      <EmptyState
        title="История пуста"
        description="Здесь появятся все попытки: специализация, грейд и решение лиги."
      />
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">История попыток</h3>
      <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
        {data.map((row) => (
          <li key={row.id}>
            <Link
              to={`/candidate/qualification/${row.id}/result`}
              className={cn(
                'flex items-center gap-3 px-4 py-3 text-sm hover:bg-secondary/50',
                row.id === currentId && 'bg-secondary/40',
              )}
            >
              <span className="w-24 shrink-0 text-xs text-muted-foreground">
                {formatDate(row.finished_at ?? row.started_at)}
              </span>
              <span className="w-24 shrink-0">{SPEC_LABEL[row.specialization]}</span>
              <span className="w-20 shrink-0 text-muted-foreground">
                {GRADE_LABEL[row.claimed_grade]}
              </span>
              <span
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase',
                  row.decision === 'confirmed'
                    ? 'border-[var(--fsp-league-confirmed)]/40 text-[var(--fsp-league-confirmed)]'
                    : row.decision === 'unconfirmed'
                      ? 'border-[var(--fsp-league-unconfirmed)]/40 text-[var(--fsp-league-unconfirmed)]'
                      : 'border-border text-muted-foreground',
                )}
              >
                {row.decision === 'confirmed'
                  ? 'подтверждён'
                  : row.decision === 'unconfirmed'
                    ? 'заявлен'
                    : row.status}
              </span>
              <span className="ml-auto tabular-nums">{row.rating ?? '—'}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** FE-06: result & history. */
export function ResultPage() {
  const { id = '' } = useParams()
  const { data: result, isLoading, isError, error, refetch } = useResult(id)
  const { data: profile } = useProfile()
  const { data: eligibility } = useEligibility(profile?.specialization || undefined)
  const [downloading, setDownloading] = useState(false)

  const downloadCard = () => {
    setDownloading(true)
    downloadPlayerCard()
      .catch((e: Error) => {
        toast.error(
          e.message === 'card_fallback_html'
            ? 'Сервер вернул HTML вместо PDF — карточка недоступна'
            : 'Не удалось скачать карточку игрока',
        )
      })
      .finally(() => setDownloading(false))
  }

  if (isLoading) {
    return (
      <section className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-8">
        <CardSkeleton />
        <CardSkeleton />
      </section>
    )
  }
  if (isError || !result) {
    return (
      <section className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState
          code={error instanceof ApiError ? error.code : undefined}
          description={
            error instanceof ApiError ? errorMessage(error.code, error.detail) : undefined
          }
          onRetry={() => void refetch()}
        />
      </section>
    )
  }

  const copy = result.decision === 'confirmed' ? DECISION_COPY.confirmed : DECISION_COPY.unconfirmed
  const cooldown = eligibility?.next_attempt_at || result.next_attempt_at || null
  const canStart = eligibility ? eligibility.can_start : !cooldown
  const fallbackMode = result.fallback?.mode ?? (result.fallback as { kind?: string } | null)?.kind
  const fallbackLabel =
    fallbackMode === 'instant'
      ? 'Экспресс-тест'
      : fallbackMode === 'short_test'
        ? 'Короткий тест'
        : null
  const startParams = new URLSearchParams({
    specialization: result.specialization,
    claimed_grade: result.claimed_grade,
  })

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-8">
      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {SPEC_LABEL[result.specialization]} · {GRADE_LABEL[result.claimed_grade]}
            </span>
            <h1 className={cn('mt-1 text-xl font-bold', copy.tone)}>{copy.title}</h1>
            <p className="mt-1 max-w-lg text-sm text-muted-foreground">{copy.note}</p>
          </div>
          {result.rating != null && (
            <div className="text-right">
              <RatingBadge rating={result.rating} ci={result.rating_ci ?? undefined} />
              <div className="text-xs text-muted-foreground">
                итоговый грейд:{' '}
                <span className="font-semibold text-foreground">
                  {result.result_grade ? GRADE_LABEL[result.result_grade] : '—'}
                </span>
              </div>
            </div>
          )}
        </div>

        <dl className="mt-5 grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg border border-border p-3">
            <dt className="text-[11px] uppercase text-muted-foreground">θ (сила)</dt>
            <dd className="text-lg font-bold tabular-nums">{result.theta?.toFixed(2) ?? '—'}</dd>
          </div>
          <div className="rounded-lg border border-border p-3">
            <dt className="text-[11px] uppercase text-muted-foreground">Погрешность</dt>
            <dd className="text-lg font-bold tabular-nums">{result.se?.toFixed(2) ?? '—'}</dd>
          </div>
          <div className="rounded-lg border border-border p-3">
            <dt className="text-[11px] uppercase text-muted-foreground">Попытка</dt>
            <dd className="text-lg font-bold">
              {result.counts_as_attempt ? 'учтена' : 'не учтена'}
            </dd>
          </div>
        </dl>
      </section>

      {(result.topics?.length || result.evidence?.length) ? (
        <section className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6">
          {result.topics?.length ? <TopicsChart topics={result.topics} /> : null}
          {result.evidence?.length ? <EvidenceChart evidence={result.evidence} /> : null}
        </section>
      ) : null}

      <section className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-6">
        <h3 className="mr-auto text-sm font-semibold">Что дальше</h3>
        {cooldown && !canStart ? <Cooldown deadline={cooldown} /> : null}
        {canStart && (
          <Button asChild>
            <Link to={`/candidate/qualification/start?${startParams.toString()}`}>
              Пройти квалификацию
            </Link>
          </Button>
        )}
        {fallbackLabel && (
          <Button variant="outline" asChild>
            <Link
              to={`/candidate/qualification/start?${startParams.toString()}&mode=fallback&kind=${encodeURIComponent(fallbackMode ?? '')}`}
            >
              <Flag className="h-4 w-4" /> {fallbackLabel}
            </Link>
          </Button>
        )}
        {result.promotion_unlocked && (
          <Button variant="outline" asChild>
            <Link to={`/candidate/qualification/start?${startParams.toString()}&kind=promotion`}>
              <Rocket className="h-4 w-4" /> Попробовать повышение
            </Link>
          </Button>
        )}
        <Button variant="ghost" onClick={downloadCard} disabled={downloading}>
          <Download className="h-4 w-4" />
          {downloading ? 'Скачиваем…' : 'Карточка игрока (PDF)'}
        </Button>
      </section>

      <HistoryList currentId={result.id} />
    </section>
  )
}
