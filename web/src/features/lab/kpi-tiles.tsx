import { CheckCircle2, XCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { ValidationReport } from '@/api/types'

type MetricTarget = {
  label: string
  sublabel: string
  value: string
  targetText: string
  pass: boolean
}

export function KpiTiles({ report }: { report: ValidationReport }) {
  const { assessment: a, matching: m } = report

  const metrics: MetricTarget[] = [
    {
      label: 'Точность грейдинга',
      sublabel: 'Exact Grade Accuracy',
      value: `${(a.exact_acc * 100).toFixed(1)}%`,
      targetText: '≥ 80.0%',
      pass: a.exact_acc >= 0.8,
    },
    {
      label: 'Смежная точность',
      sublabel: 'Adjacent Accuracy (±1 грейд)',
      value: `${(a.adjacent_acc * 100).toFixed(1)}%`,
      targetText: '≥ 98.0%',
      pass: a.adjacent_acc >= 0.98,
    },
    {
      label: 'Каппа Коэна (QWK)',
      sublabel: 'Quadratic Weighted Kappa',
      value: a.qwk.toFixed(3),
      targetText: '≥ 0.800',
      pass: a.qwk >= 0.8,
    },
    {
      label: 'Надежность ретеста',
      sublabel: 'Retest Same Grade & r',
      value: `${(a.retest_same_grade * 100).toFixed(1)}% (r = ${a.retest_r.toFixed(2)})`,
      targetText: '≥ 80.0%, r ≥ 0.85',
      pass: a.retest_same_grade >= 0.8 && a.retest_r >= 0.85,
    },
    {
      label: 'Медианная длина теста',
      sublabel: 'CAT questions count',
      value: `${Math.round(a.median_len)} вопр.`,
      targetText: '≤ 14 вопросов',
      pass: a.median_len <= 14,
    },
    {
      label: 'Коллизии генератора',
      sublabel: 'Collision & Gen Errors',
      value: `${(a.collision_rate * 100).toFixed(3)}% (ошибок: ${a.generator_errors})`,
      targetText: '≤ 0.100%, ошибок = 0',
      pass: a.collision_rate <= 0.001 && a.generator_errors === 0,
    },
    {
      label: 'Паритет без ФСП',
      sublabel: 'Non-FSP candidate parity',
      value: `${(m.non_fsp_parity * 100).toFixed(1)}%`,
      targetText: '≥ 80.0%',
      pass: m.non_fsp_parity >= 0.8,
    },
    {
      label: 'Латентность скоринга',
      sublabel: 'Pool ranking p95',
      value: `${Math.round(m.pool_p95_ms)} мс`,
      targetText: '< 300 мс',
      pass: m.pool_p95_ms < 300,
    },
  ]

  const passCount = metrics.filter((m) => m.pass).length
  const missCount = metrics.length - passCount

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
        <span>Ключевые психометрические показатели</span>
        <span className="font-medium">
          Выполнено: <strong className="text-plus">{passCount}</strong> · Промахов:{' '}
          <strong className="text-minus">{missCount}</strong>
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((item) => (
          <Card
            key={item.label}
            className={`p-4 gap-2 transition-colors ${
              !item.pass ? 'border-destructive/30 bg-destructive/5' : ''
            }`}
          >
            <CardContent className="p-0 flex flex-col justify-between h-full">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-medium text-foreground">{item.label}</div>
                  <div className="text-[11px] text-muted-foreground">{item.sublabel}</div>
                </div>
                <Badge
                  variant={item.pass ? 'success' : 'danger'}
                  className="shrink-0 text-[10px] font-semibold"
                >
                  {item.pass ? (
                    <CheckCircle2 className="h-3 w-3 mr-0.5 text-plus" />
                  ) : (
                    <XCircle className="h-3 w-3 mr-0.5 text-minus" />
                  )}
                  {item.pass ? 'PASS' : 'MISS'}
                </Badge>
              </div>
              <div className="mt-2">
                <div
                  className={`text-xl font-bold tabular-nums tracking-tight ${
                    !item.pass ? 'text-minus' : 'text-foreground'
                  }`}
                >
                  {item.value}
                </div>
                <div className="text-[11px] text-muted-foreground">Цель: {item.targetText}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
