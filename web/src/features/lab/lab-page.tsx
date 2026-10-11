import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError } from '@/api/client'
import { useLabReport, useTestTwins } from '@/api/lab'
import type {
  LabTwinItem,
  LabTwinsResponse,
  TwinInstanceView,
  ValidationAssessment,
  ValidationReport,
} from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CardSkeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { MarkdownText, CodeBlock } from '@/features/qualification-runner/render'
import {
  confusionCells,
  formatDateTime,
  formatMillis,
  formatPercent,
  heatIntensity,
  leakRows,
  maxCell,
  sortSystems,
  tifPoints,
} from '@/features/lab/report'
import {
  difficultyRatio,
  formatDuration,
  twinDuration,
  twinMeanDifficulty,
  twinTopicCounts,
} from '@/features/lab/twins'

const GRADES = ['intern', 'junior', 'middle', 'senior']
const SPECS = ['backend', 'frontend', 'ml_data'] as const

const TABS = [
  { key: 'report', label: 'Отчёт' },
  { key: 'twins', label: 'Двойники тестов' },
] as const

type TabKey = (typeof TABS)[number]['key']

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="gap-0">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      {hint && (
        <CardContent>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </CardContent>
      )}
    </Card>
  )
}

function ConfusionHeatmap({ assessment }: { assessment: ValidationAssessment }) {
  const cells = useMemo(() => confusionCells(assessment.confusion), [assessment.confusion])
  const max = useMemo(() => maxCell(assessment.confusion), [assessment.confusion])
  const size = GRADES.length

  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="sr-only">
        Матрица ошибок: строки — верная оценка, столбцы — предсказанная.
      </figcaption>
      <div className="overflow-x-auto">
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `minmax(4rem,auto) repeat(${size}, minmax(3rem,1fr))` }}
          role="img"
          aria-label="Матрица ошибок предсказанных оценок"
        >
          <div />
          {GRADES.map((g) => (
            <div key={g} className="text-center text-xs text-muted-foreground">
              {GRADE_LABEL[g]}
            </div>
          ))}
          {GRADES.map((rowGrade, r) => (
            <div key={rowGrade} className="contents">
              <div className="flex items-center text-xs text-muted-foreground">
                {GRADE_LABEL[rowGrade]}
              </div>
              {GRADES.map((colGrade, c) => {
                const value = cells[r * size + c]?.value ?? 0
                const intensity = heatIntensity(value, max)
                return (
                  <div
                    key={colGrade}
                    className={
                      intensity > 0.55
                        ? 'flex aspect-square items-center justify-center rounded-md text-sm font-semibold text-primary-foreground'
                        : 'flex aspect-square items-center justify-center rounded-md text-sm font-semibold text-foreground'
                    }
                    style={{ backgroundColor: 'var(--fsp-accent)', opacity: 0.12 + intensity * 0.88 }}
                  >
                    {value}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <table className="sr-only">
        <caption>Матрица ошибок предсказанных оценок</caption>
        <thead>
          <tr>
            <th>Истина</th>
            {GRADES.map((g) => (
              <th key={g}>{GRADE_LABEL[g]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {GRADES.map((rowGrade, r) => (
            <tr key={rowGrade}>
              <th>{GRADE_LABEL[rowGrade]}</th>
              {GRADES.map((colGrade, c) => (
                <td key={colGrade}>{cells[r * size + c]?.value ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

function TifChart({ assessment }: { assessment: ValidationAssessment }) {
  const data = useMemo(() => tifPoints(assessment.tif), [assessment.tif])
  return (
    <figure className="flex flex-col gap-3">
      <div className="h-64" role="img" aria-label="Кривая тестовой информации по уровню способности">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--fsp-line)" />
            <XAxis dataKey="theta" type="number" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="info"
              name="Информация"
              stroke="var(--fsp-brand)"
              strokeWidth={2}
              dot
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Текстовая альтернатива кривой тестовой информации</caption>
        <thead>
          <tr>
            <th>Способность (theta)</th>
            <th>Информация</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.theta}>
              <td>{p.theta}</td>
              <td>{p.info}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

function LeakChart({ assessment }: { assessment: ValidationAssessment }) {
  const data = useMemo(
    () =>
      leakRows(assessment.leak_attack).map((p) => ({
        leak: formatPercent(p.leak_share),
        static: p.static_dtheta,
        parametric: p.parametric_dtheta,
      })),
    [assessment.leak_attack],
  )
  return (
    <figure className="flex flex-col gap-3">
      <div className="h-64" role="img" aria-label="Сдвиг оценки при утечке ответов">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--fsp-line)" />
            <XAxis dataKey="leak" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="static" name="Статический" fill="var(--fsp-brand)" />
            <Bar dataKey="parametric" name="Параметрический" fill="var(--fsp-secondary)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Текстовая альтернатива графика утечки ответов</caption>
        <thead>
          <tr>
            <th>Доля утечки</th>
            <th>Статический Δθ</th>
            <th>Параметрический Δθ</th>
          </tr>
        </thead>
        <tbody>
          {leakRows(assessment.leak_attack).map((p) => (
            <tr key={p.leak_share}>
              <td>{formatPercent(p.leak_share)}</td>
              <td>{p.static_dtheta}</td>
              <td>{p.parametric_dtheta}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

function SystemsTable({ report }: { report: ValidationReport }) {
  const systems = useMemo(() => sortSystems(report.matching.systems), [report.matching.systems])
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Сравнение систем ранжирования</caption>
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th scope="col" className="py-2 pr-4">Система</th>
            <th scope="col" className="py-2 pr-4">nDCG@10</th>
            <th scope="col" className="py-2 pr-4">P@10</th>
            <th scope="col" className="py-2 pr-4">R@50</th>
            <th scope="col" className="py-2">MRR</th>
          </tr>
        </thead>
        <tbody>
          {systems.map((s) => (
            <tr key={s.name} className="border-b border-border last:border-0">
              <th scope="row" className="py-2 pr-4 text-left font-medium">{s.name}</th>
              {(['ndcg10', 'p10', 'r50', 'mrr'] as const).map((metric) => (
                <td key={metric} className="py-2 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="w-12 tabular-nums">{formatPercent(s[metric])}</span>
                    <span className="h-1.5 w-16 rounded-full bg-muted" aria-hidden="true">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${Math.min(1, Math.max(0, s[metric])) * 100}%`,
                          backgroundColor: 'var(--fsp-score-fsp)',
                        }}
                      />
                    </span>
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReportSection() {
  const { data, isPending, isError, error, refetch } = useLabReport()

  if (isPending) return <CardSkeleton />

  if (isError || !data) {
    const code = error instanceof ApiError ? error.code : undefined
    return (
      <ErrorState
        title="Отчёт недоступен"
        description={errorMessage(code, 'Не удалось загрузить отчёт валидации.')}
        code={code}
        onRetry={() => void refetch()}
      />
    )
  }

  const { assessment, matching } = data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">Отчёт о валидации</h2>
          {data.synthetic_fixture && <Badge variant="warning">фикстура</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">
          Качество адаптивной оценки и ранжирования: метрики, кривые и стресс-тесты.
        </p>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          <div className="flex gap-1">
            <dt>Сгенерировано:</dt>
            <dd className="font-medium text-foreground">{formatDateTime(data.generated_at)}</dd>
          </div>
          <div className="flex gap-1">
            <dt>git:</dt>
            <dd className="font-mono">{data.git_sha}</dd>
          </div>
        </dl>
      </div>

      <section className="grid gap-3 sm:grid-cols-3">
        <Kpi label="Точность (exact)" value={formatPercent(assessment.exact_acc)} />
        <Kpi label="QWK" value={formatPercent(assessment.qwk)} />
        <Kpi
          label="Retest · та же оценка"
          value={formatPercent(assessment.retest_same_grade)}
          hint={`r = ${assessment.retest_r}`}
        />
        <Kpi label="Соседняя точность" value={formatPercent(assessment.adjacent_acc)} />
        <Kpi label="Медианная длина" value={`${assessment.median_len}`} hint="заданий" />
        <Kpi label="Макс. экспозиция семьи" value={formatPercent(assessment.max_family_exposure)} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Матрица ошибок</CardTitle>
          <CardDescription>Строки — истинная оценка, столбцы — предсказанная.</CardDescription>
        </CardHeader>
        <CardContent>
          <ConfusionHeatmap assessment={assessment} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Тестовая информация</CardTitle>
          <CardDescription>Сколько информации несёт тест на каждом уровне способности.</CardDescription>
        </CardHeader>
        <CardContent>
          <TifChart assessment={assessment} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Атака утечкой ответов</CardTitle>
          <CardDescription>Сдвиг оценки Δθ при разной доле подсмотренных ответов.</CardDescription>
        </CardHeader>
        <CardContent>
          <LeakChart assessment={assessment} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ранжирование и матчинг</CardTitle>
          <CardDescription>Сравнение систем по умолчанию против наших бейзлайнов.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-3 text-sm">
            <span className="rounded-lg bg-muted px-3 py-1.5">
              Кандидатов: <strong>{matching.candidates}</strong>
            </span>
            <span className="rounded-lg bg-muted px-3 py-1.5">
              Потребностей: <strong>{matching.needs}</strong>
            </span>
            <span className="rounded-lg bg-muted px-3 py-1.5">
              Паритет вне FSP: <strong>{formatPercent(matching.non_fsp_parity)}</strong>
            </span>
            <span className="rounded-lg bg-muted px-3 py-1.5">
              p95 пула: <strong>{formatMillis(matching.pool_p95_ms)}</strong>
            </span>
          </div>
          <SystemsTable report={data} />
        </CardContent>
      </Card>

      <footer className="flex flex-wrap gap-4 border-t border-border pt-4 text-xs text-muted-foreground">
        <span>Ошибки генерации: {assessment.generator_errors}</span>
        <span>Коллизии: {formatPercent(assessment.collision_rate)}</span>
        <span>Симуляций: {assessment.simulees}</span>
      </footer>
    </div>
  )
}

function DifficultyBar({ b }: { b: number }) {
  return (
    <div className="flex items-center gap-2" aria-label={`Сложность b=${b}`}>
      <span className="h-1.5 w-24 rounded-full bg-muted" aria-hidden="true">
        <span
          className="block h-full rounded-full"
          style={{ width: `${difficultyRatio(b) * 100}%`, backgroundColor: 'var(--fsp-score-semantic)' }}
        />
      </span>
      <span className="font-mono text-xs text-muted-foreground">b={b}</span>
    </div>
  )
}

function InstancePreview({ instance }: { instance: TwinInstanceView }) {
  return (
    <div className="flex flex-col gap-3">
      <MarkdownText text={instance.stem_md} className="text-sm leading-relaxed" />
      {instance.code && <CodeBlock code={instance.code.text} lang={instance.code.lang} />}
      {instance.options && instance.options.length > 0 ? (
        <ol className="flex flex-col gap-1.5">
          {instance.options.map((option, i) => (
            <li key={option.id} className="flex items-start gap-2 text-sm">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-xs text-muted-foreground">
                {String.fromCharCode(65 + i)}
              </span>
              <MarkdownText text={option.text_md} className="min-w-0 flex-1" />
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-xs text-muted-foreground">
          {instance.input === 'number' ? 'Числовой ответ' : 'Развёрнутый ответ'}
        </p>
      )}
    </div>
  )
}

function TwinColumn({
  title,
  twins,
  variant,
}: {
  title: string
  twins: LabTwinItem[]
  variant: 'a' | 'b'
}) {
  const mean = twinMeanDifficulty(twins)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <DifficultyBar b={Math.round(mean * 1000) / 1000} />
      </div>
      {twins.map((twin, i) => (
        <Card key={`${twin.family_id}-${variant}`} className="gap-3 py-4">
          <CardHeader className="gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {i + 1}. <code className="font-mono">{twin.topic}</code> ·{' '}
                {GRADE_LABEL[twin.level] ?? twin.level}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatDuration(twin.time_limit_s)}
              </span>
            </div>
            <DifficultyBar b={twin.b} />
          </CardHeader>
          <CardContent>
            <InstancePreview instance={variant === 'a' ? twin.instance_a : twin.instance_b} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function TwinsSection({ positionId }: { positionId: string | null }) {
  const [specialization, setSpecialization] = useState<string>('backend')
  const [grade, setGrade] = useState<string>('middle')
  const { data, isPending, isError, error, refetch } = useTestTwins({
    positionId,
    specialization,
    grade,
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Двойники тестов</h2>
        <p className="text-sm text-muted-foreground">
          JD → блупринт → два уникальных теста с одинаковым профилем сложности.
        </p>
      </div>

      {!positionId && (
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Специализация
            <select
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
              className="rounded-md border border-input bg-card px-3 py-1.5 text-sm text-foreground"
            >
              {SPECS.map((s) => (
                <option key={s} value={s}>
                  {SPEC_LABEL[s] ?? s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Целевой грейд
            <select
              value={grade}
              onChange={(e) => setGrade(e.target.value)}
              className="rounded-md border border-input bg-card px-3 py-1.5 text-sm text-foreground"
            >
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  {GRADE_LABEL[g]}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {isPending ? (
        <CardSkeleton />
      ) : isError || !data ? (
        <ErrorState
          title="Не удалось построить двойники"
          description={errorMessage(
            error instanceof ApiError ? error.code : undefined,
            'Попробуйте другую специализацию или грейд.',
          )}
          code={error instanceof ApiError ? error.code : undefined}
          onRetry={() => void refetch()}
        />
      ) : (
        <TwinsResult data={data} />
      )}
    </div>
  )
}

function TwinsResult({ data }: { data: LabTwinsResponse }) {
  const topics = useMemo(() => twinTopicCounts(data.twins), [data.twins])
  const mean = twinMeanDifficulty(data.twins)
  const duration = twinDuration(data.twins)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <strong>{data.position_title ?? `${SPEC_LABEL[data.specialization] ?? data.specialization} · ${GRADE_LABEL[data.grade] ?? data.grade}`}</strong>
          <Badge variant="secondary">{data.twins.length} слотов</Badge>
          <Badge variant="success">Профиль совпадает</Badge>
          <Badge variant="secondary">Длительность: {formatDuration(duration)}</Badge>
          <Badge variant="secondary">Средняя сложность: b={Math.round(mean * 1000) / 1000}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Блупринт:</span>
          {topics.map((t) => (
            <span key={t.topic} className="rounded-full bg-muted px-2.5 py-0.5 text-xs">
              <code className="font-mono">{t.topic}</code> × {t.count}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <TwinColumn title="Вариант А" twins={data.twins} variant="a" />
        <TwinColumn title="Вариант Б" twins={data.twins} variant="b" />
      </div>

      <p className="text-xs text-muted-foreground">
        Показано только то, что видит кандидат: ключи ответов не раскрываются.
      </p>
    </div>
  )
}

export function LabPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab: TabKey = searchParams.get('tab') === 'twins' ? 'twins' : 'report'
  const positionId = searchParams.get('position_id')

  const selectTab = (next: TabKey) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'report') params.delete('tab')
    else params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-bold">Лаборатория валидации</h1>
        <div role="tablist" aria-label="Разделы лаборатории" className="flex gap-1 border-b border-border">
          {TABS.map((t) => (
            <button
              key={t.key}
              id={`lab-tab-${t.key}`}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              aria-controls={`lab-panel-${t.key}`}
              onClick={() => selectTab(t.key)}
              className={cn(
                '-mb-px rounded-t-lg border-b-2 px-4 py-2 text-sm transition-colors',
                tab === t.key
                  ? 'border-primary font-semibold text-[var(--fsp-accent-strong)]'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div
        role="tabpanel"
        id={`lab-panel-${tab}`}
        aria-labelledby={`lab-tab-${tab}`}
        tabIndex={-1}
      >
        {tab === 'report' ? <ReportSection /> : <TwinsSection positionId={positionId} />}
      </div>
    </section>
  )
}
