import { TriangleAlert } from 'lucide-react'
import { useLabReport } from '@/api/lab'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { RowSkeleton } from '@/components/ui/skeleton'
import { ConfusionMatrix } from './components/confusion-matrix'
import { TifChart, LeakChart } from './components/charts'
import { SystemsTable } from './components/systems-table'
import type { ValidationReport } from '@/api/types'

const pct = (v: number) => `${Math.round(v * 100)}%`
const num = (v: number) => v.toLocaleString('ru-RU')
const dateFmt = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-2xl font-bold tabular-nums">{value}</span>
      {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
    </div>
  )
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function FixtureBanner() {
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-destructive"
    >
      <TriangleAlert className="h-5 w-5 shrink-0" />
      <p className="text-sm font-semibold">FIXTURE — синтетический отчёт для демонстрации.</p>
      <p className="text-sm text-destructive/90">
        Числа не отражают работу продакшена; в выступление перед жюри включать нельзя.
      </p>
    </div>
  )
}

function Meta({ report }: { report: ValidationReport }) {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
      <div>
        <dt className="inline">Сгенерировано: </dt>
        <dd className="inline font-mono tabular-nums">{dateFmt.format(new Date(report.generated_at))}</dd>
      </div>
      <div>
        <dt className="inline">git: </dt>
        <dd className="inline font-mono">{report.git_sha.slice(0, 7)}</dd>
      </div>
      <div>
        <dt className="inline">Симулянты: </dt>
        <dd className="inline font-mono tabular-nums">{num(report.assessment.simulees)}</dd>
      </div>
      <div>
        <dt className="inline">Кандидатов в симуляции: </dt>
        <dd className="inline font-mono tabular-nums">{num(report.matching.candidates)}</dd>
      </div>
    </dl>
  )
}

export function LabPage() {
  const { data, isLoading, isError, error, refetch } = useLabReport()

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4 py-8">
        <RowSkeleton count={3} />
        <RowSkeleton count={2} />
      </div>
    )
  }

  if (isError || !data) {
    const message =
      error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось загрузить отчёт.'
    return (
      <section className="mx-auto flex max-w-xl flex-col items-center gap-4 p-4 py-10 text-center">
        <h1 className="text-lg font-bold">Validation Lab</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" onClick={() => refetch()}>
          Повторить
        </Button>
      </section>
    )
  }

  const { assessment, matching } = data

  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-4 p-4 py-10">
      <header className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Validation Lab
          </span>
          <h1 className="text-2xl font-bold">Качество теста и матчинга</h1>
          <p className="text-sm text-muted-foreground">
            Метрики генерируются скриптом «make validate» по симуляции прохождения теста и прогону
            матчинга: точность оценки, надёжность, устойчивость к утечкам, качество ранжирования.
          </p>
        </div>
        {data.synthetic_fixture && <FixtureBanner />}
        <Meta report={data} />
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Ключевые метрики">
        <Kpi label="Точность" value={pct(assessment.exact_acc)} sub={`соседний грейд ${pct(assessment.adjacent_acc)}`} />
        <Kpi label="QWK" value={assessment.qwk.toFixed(2)} sub="взвешенная каппа Козна" />
        <Kpi label="Ретест" value={pct(assessment.retest_same_grade)} sub={`корреляция r = ${assessment.retest_r.toFixed(2)}`} />
        <Kpi label="Коллизии" value={pct(assessment.collision_rate)} sub={`ошибок генерации: ${assessment.generator_errors}`} />
      </section>

      <section className="grid gap-3 md:grid-cols-2" aria-label="Прочие метрики теста">
        <Kpi label="Медианная длина теста" value={`${assessment.median_len} заданий`} sub="по адаптивной трассе" />
        <Kpi label="Максимальная экспозиция семейства" value={`${assessment.max_family_exposure}×`} sub="защита от заучивания" />
      </section>

      <SectionCard title="Матрица ошибок" description="Фактический грейд против предсказанного. Диагональ — совпадения, вне диагонали — расхождения (допустимо соседство грейдов).">
        <ConfusionMatrix matrix={assessment.confusion} />
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Кривая информации (TIF)" description="Сколько информации даёт тест на каждом уровне способности. Пик в районе theta = 0 — целевая зона оценки.">
          <TifChart theta={assessment.tif.theta} info={assessment.tif.info} />
        </SectionCard>
        <SectionCard title="Атаки на утечки" description="Сдвиг результата (Δθ) при доступе к доле заданий. Параметрический пул деградирует позже статического.">
          <LeakChart rows={assessment.leak_attack} />
        </SectionCard>
      </div>

      <SectionCard
        title="Матчинг"
        description={`Симуляция: ${num(matching.candidates)} кандидатов, ${num(matching.needs)} потребностей. Паритет с не-FSP: ${pct(matching.non_fsp_parity)}, p95 латентности: ${matching.pool_p95_ms} мс.`}
      >
        <SystemsTable systems={matching.systems} />
      </SectionCard>
    </section>
  )
}