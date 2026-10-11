import { useState } from 'react'
import {
  FlaskConical,
  RefreshCw,
  GitCommit,
  Calendar,
  AlertTriangle,
  FileCheck2,
  Split,
  Layers,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CardSkeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { useLabReport } from '@/api/lab'
import { KpiTiles } from '@/features/lab/kpi-tiles'
import { TargetsTable } from '@/features/lab/targets-table'
import { ConfusionMatrix } from '@/features/lab/confusion-matrix'
import { TifChart } from '@/features/lab/tif-chart'
import { LeakAttackChart } from '@/features/lab/leak-attack-chart'
import { MatchingSystemsTable } from '@/features/lab/matching-systems-table'
import { TwinsSection } from '@/features/lab/twins-section'
import { FamiliesSection } from '@/features/lab/families-section'

type TabType = 'report' | 'twins' | 'families'

export function LabPage() {
  const [activeTab, setActiveTab] = useState<TabType>('report')
  const { data: report, isLoading, isError, refetch, isFetching } = useLabReport()

  const formattedDate = report?.generated_at
    ? new Date(report.generated_at).toLocaleString('ru-RU', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : null

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8">
      {/* Header */}
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FlaskConical className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-heading">
                  Психометрическая лаборатория (Validation Lab)
                </h1>
              </div>
              <p className="text-xs text-muted-foreground">
                Аудит психометрических моделей IRT, защита от утечек заданий и бенчмарк алгоритмов подбора
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {report && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground mr-2">
                {formattedDate && (
                  <span className="inline-flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {formattedDate}
                  </span>
                )}
                <span className="inline-flex items-center gap-1 font-mono">
                  <GitCommit className="h-3 w-3" />
                  {report.git_sha}
                </span>
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </div>

        {/* Red Fixture Banner per FE-13 spec */}
        {report?.synthetic_fixture && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg border-2 border-destructive bg-destructive/10 p-3.5 text-destructive"
          >
            <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
            <div className="text-xs space-y-1">
              <div className="font-bold uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                <span className="rounded bg-destructive px-1.5 py-0.5 text-white font-black text-[10px]">
                  FIXTURE
                </span>
                Синтетический фикстурный отчет (synthetic_fixture: true)
              </div>
              <p className="text-foreground/80 leading-normal">
                Данные загружены из тестовой фикстуры <code>report.fixture.json</code>. Настоящие психометрические
                расчеты по 10 000 симуляций и бенчмарку формируются скриптом <code>python -m validation.run</code>.
              </p>
            </div>
          </div>
        )}

        {/* Tab Controls */}
        <div className="flex items-center gap-2 border-b border-border pt-2">
          <button
            type="button"
            onClick={() => setActiveTab('report')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${
              activeTab === 'report'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileCheck2 className="h-3.5 w-3.5" />
            Валидационный отчет
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('twins')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${
              activeTab === 'twins'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Split className="h-3.5 w-3.5" />
            Тесты-близнецы
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('families')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${
              activeTab === 'families'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            Каталог семейств и дрейф
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main>
        {activeTab === 'report' && (
          <div className="space-y-6">
            {isLoading ? (
              <div className="space-y-4">
                <CardSkeleton />
                <CardSkeleton />
              </div>
            ) : isError || !report ? (
              <ErrorState
                title="Не удалось загрузить психометрический отчет"
                description="Проверьте соединение с бэкендом или статус /api/lab/report."
                onRetry={() => void refetch()}
              />
            ) : (
              <>
                {/* 1. KPI Target Tiles */}
                <section aria-labelledby="kpi-heading">
                  <h2 id="kpi-heading" className="sr-only">
                    Ключевые показатели валидации
                  </h2>
                  <KpiTiles report={report} />
                </section>

                {/* 2. Full 15-target Engineering Audit Table */}
                <section aria-labelledby="targets-heading">
                  <h2 id="targets-heading" className="sr-only">
                    Аудит 15 инженерных целей архитектуры
                  </h2>
                  <TargetsTable report={report} />
                </section>

                {/* 3. Confusion Matrix Heatmap */}
                <section aria-labelledby="confusion-heading">
                  <h2 id="confusion-heading" className="sr-only">
                    Матрица ошибок классификации
                  </h2>
                  <ConfusionMatrix matrix={report.assessment.confusion} />
                </section>

                {/* 3. TIF Curve & Leak Attack Bar Chart */}
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <section aria-labelledby="tif-heading">
                    <h2 id="tif-heading" className="sr-only">
                      Кривая информации теста
                    </h2>
                    <TifChart tif={report.assessment.tif} />
                  </section>
                  <section aria-labelledby="leak-heading">
                    <h2 id="leak-heading" className="sr-only">
                      Устойчивость к утечкам вопросов
                    </h2>
                    <LeakAttackChart data={report.assessment.leak_attack} />
                  </section>
                </div>

                {/* 4. Matching Systems Benchmark Table */}
                <section aria-labelledby="systems-heading">
                  <h2 id="systems-heading" className="sr-only">
                    Бенчмарк систем матчинга
                  </h2>
                  <MatchingSystemsTable systems={report.matching.systems} />
                </section>
              </>
            )}
          </div>
        )}

        {activeTab === 'twins' && <TwinsSection />}

        {activeTab === 'families' && <FamiliesSection />}
      </main>
    </div>
  )
}
