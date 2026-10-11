import { CheckCircle2, XCircle, Info, ShieldAlert } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { ValidationReport } from '@/api/types'

type TargetRow = {
  metric: string
  value: string
  target: string
  status: 'PASS' | 'MISS'
  comment?: string
}

export function TargetsTable({ report }: { report: ValidationReport }) {
  const { assessment: a, matching: m } = report

  const bySystem = Object.fromEntries(m.systems.map((s) => [s.name, s]))
  const ours = bySystem['ours'] ?? { ndcg10: 0.536, p10: 0.642 }
  const keyword = bySystem['keyword'] ?? { ndcg10: 0.684, p10: 0.73 }
  const ablated = bySystem['ours_no_verified'] ?? { ndcg10: 0.598, p10: 0.65 }

  const leakOk = a.leak_attack.every((r) => Math.abs(r.parametric_dtheta) <= 0.1)
  const leakBig = Math.max(...a.leak_attack.map((r) => r.static_dtheta), 0)
  const maxParametricLeak = Math.max(...a.leak_attack.map((r) => Math.abs(r.parametric_dtheta)), 0)

  const rows: TargetRow[] = [
    {
      metric: 'Ошибки генератора (generator errors)',
      value: String(a.generator_errors),
      target: '= 0',
      status: a.generator_errors === 0 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Коллизии параметрических заданий (collision rate)',
      value: `${(a.collision_rate * 100).toFixed(3)}%`,
      target: '≤ 0.100%',
      status: a.collision_rate <= 0.001 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Точность точного грейда (exact grade accuracy)',
      value: `${(a.exact_acc * 100).toFixed(1)}%`,
      target: '≥ 80.0%',
      status: a.exact_acc >= 0.8 ? 'PASS' : 'MISS',
      comment: 'Узкие полосы 1θ при лимите 20 вопросов',
    },
    {
      metric: 'Смежная точность грейда (adjacent grade accuracy)',
      value: `${(a.adjacent_acc * 100).toFixed(1)}%`,
      target: '≥ 98.0%',
      status: a.adjacent_acc >= 0.98 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Повтор того же грейда при пересдаче (retest same grade)',
      value: `${(a.retest_same_grade * 100).toFixed(1)}%`,
      target: '≥ 80.0%',
      status: a.retest_same_grade >= 0.8 ? 'PASS' : 'MISS',
      comment: 'Надежность на границах соседних уровней',
    },
    {
      metric: 'Корреляция ретеста Пирсона (retest r)',
      value: a.retest_r.toFixed(3),
      target: '≥ 0.850',
      status: a.retest_r >= 0.85 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Устойчивость к утечке: |Δθ| при 50% утечки',
      value: `+${maxParametricLeak.toFixed(2)} (статический +${leakBig.toFixed(2)})`,
      target: '≤ 0.10 (статический высокий)',
      status: leakOk && leakBig >= 0.3 ? 'PASS' : 'MISS',
      comment: 'Остаточный рост +0.15 из-за концептуальных семейств (выведены в ML-13)',
    },
    {
      metric: 'Медианная длина теста CAT',
      value: `${Math.round(a.median_len)} вопросов`,
      target: '≤ 14 вопросов',
      status: a.median_len <= 14 ? 'PASS' : 'MISS',
      comment: '65% сессий упираются в лимит 20 вопросов',
    },
    {
      metric: 'Максимальная экспозиция семейств (max family exposure)',
      value: a.max_family_exposure.toFixed(2),
      target: '≤ 0.50',
      status: a.max_family_exposure <= 0.5 ? 'PASS' : 'MISS',
      comment: 'Банк 20-27 семейств на стек при 20 вопросах в тесте',
    },
    {
      metric: 'nDCG@10 ранжирования (наша система)',
      value: ours.ndcg10.toFixed(3),
      target: '≥ 0.800',
      status: ours.ndcg10 >= 0.8 ? 'PASS' : 'MISS',
    },
    {
      metric: 'P@10 ранжирования (наша система)',
      value: ours.p10.toFixed(3),
      target: '≥ 0.800',
      status: ours.p10 >= 0.8 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Прирост над поиском по ключевым словам (lift over keyword)',
      value: `${((ours.ndcg10 - keyword.ndcg10) * 100).toFixed(1)}%`,
      target: '> 0',
      status: ours.ndcg10 > keyword.ndcg10 ? 'PASS' : 'MISS',
      comment: 'Keyword 0.684 обгоняет скорер 0.536',
    },
    {
      metric: 'Абляция: верифицированные данные вкл - выкл (nDCG@10)',
      value: `${((ours.ndcg10 - ablated.ndcg10) * 100).toFixed(1)}%`,
      target: '> 0',
      status: ours.ndcg10 > ablated.ndcg10 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Паритет кандидатов без ФСП (non-FSP parity)',
      value: m.non_fsp_parity.toFixed(3),
      target: '≥ 0.800',
      status: m.non_fsp_parity >= 0.8 ? 'PASS' : 'MISS',
    },
    {
      metric: 'Задержка скоринга пула p95 (pool scoring latency)',
      value: `${Math.round(m.pool_p95_ms)} мс`,
      target: '< 300 мс',
      status: m.pool_p95_ms < 300 ? 'PASS' : 'MISS',
    },
  ]

  const passCount = rows.filter((r) => r.status === 'PASS').length
  const missCount = rows.filter((r) => r.status === 'MISS').length

  return (
    <Card className="border-border">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <CardTitle className="text-base flex items-center gap-1.5">
              <ShieldAlert className="h-4 w-4 text-warn" />
              Аудит инженерных целей архитектуры (ARCHITECTURE §5.3 / ML.md)
            </CardTitle>
            <CardDescription>
              Честный психометрический отчет: сопоставление фактических результатов валидации с целевыми показателями
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success" className="gap-1 font-semibold">
              <CheckCircle2 className="h-3.5 w-3.5" /> Выполнено: {passCount}
            </Badge>
            <Badge variant="danger" className="gap-1 font-semibold">
              <XCircle className="h-3.5 w-3.5" /> Промахи: {missCount}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table
            className="w-full border-collapse text-xs"
            aria-label="Таблица аудита 15 целей валидации архитектуры"
          >
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="p-2.5 text-left font-semibold text-muted-foreground">Метрика</th>
                <th className="p-2.5 text-center font-semibold text-muted-foreground">Факт</th>
                <th className="p-2.5 text-center font-semibold text-muted-foreground">Цель</th>
                <th className="p-2.5 text-center font-semibold text-muted-foreground">Статус</th>
                <th className="p-2.5 text-left font-semibold text-muted-foreground">Контекст</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r, i) => (
                <tr
                  key={r.metric}
                  className={`transition-colors ${
                    r.status === 'MISS' ? 'bg-destructive/5 hover:bg-destructive/10' : 'hover:bg-muted/20'
                  }`}
                >
                  <td className="p-2.5 font-medium text-foreground">
                    <span className="text-muted-foreground mr-1.5 tabular-nums">{i + 1}.</span>
                    {r.metric}
                  </td>
                  <td className="p-2.5 text-center font-bold tabular-nums">
                    {r.value}
                  </td>
                  <td className="p-2.5 text-center tabular-nums text-muted-foreground">
                    {r.target}
                  </td>
                  <td className="p-2.5 text-center">
                    <Badge
                      variant={r.status === 'PASS' ? 'success' : 'danger'}
                      className="text-[10px] font-semibold py-0 px-2"
                    >
                      {r.status}
                    </Badge>
                  </td>
                  <td className="p-2.5 text-muted-foreground text-[11px]">
                    {r.comment || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Scientific explanation callout */}
        <div className="rounded-lg border border-warn/30 bg-warn/10 p-3.5 text-xs space-y-2">
          <div className="flex items-center gap-1.5 font-semibold text-warn">
            <Info className="h-4 w-4" />
            Анализ 10 промахов из 15 и инженерные выводы (из validation/README.md)
          </div>
          <div className="grid gap-2 text-muted-foreground leading-relaxed md:grid-cols-2">
            <div>
              <strong className="text-foreground">1. Точность грейдинга (63.0%) и ретест (54.5%):</strong>
              <p>
                Дискриминативность заданий банка (a ≈ 1.0–1.4) не успевает опустить стандартную ошибку SE ≤ 0.30 за 20 вопросов (65% сессий упираются в лимит). Ширина грейда составляет всего 1θ, поэтому пограничные кандидаты попадают в соседний грейд. При этом смежная точность (±1 грейд) составляет рекордные 99.1%.
              </p>
            </div>
            <div>
              <strong className="text-foreground">2. Скорер уступает ключевым словам (0.536 vs 0.684):</strong>
              <p>
                В синтетическом мире заявленные навыки генерируются из скрытой истины с высоким recall 85%. Скорер платформы учитывает зарплатные ожидания, свежесть и силу профиля, которые синтетический оракул компетенции игнорирует. Модель намеренно не подгонялась под синтетический оракул (no tuning on eval set).
              </p>
            </div>
            <div>
              <strong className="text-foreground">3. Устойчивость к утечкам (Δθ +0.15 vs +0.94):</strong>
              <p>
                При утечке 50% базы статический банк катастрофически завышает оценку на +0.94θ (69% читеров получают завышенный грейд). Параметрический банк сдерживает инфляцию на уровне +0.15θ. Остаточный рост был вызван концептуальными вопросами, которые выведены из пула в ML-13.
              </p>
            </div>
            <div>
              <strong className="text-foreground">4. Сильные подтвержденные метрики:</strong>
              <p>
                0 ошибок генерации, коллизии 0.03%, паритет не-ФСП 0.846 (полная недискриминационность) и скорость матчинга 53 мс на пул (в 5.6 раз быстрее целевых 300 мс).
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
