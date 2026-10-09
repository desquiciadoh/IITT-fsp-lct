import { Activity, CircleOff, Percent } from 'lucide-react'
import type { NeedHealth } from '@/api/types'

const REASON_LABEL: Record<string, string> = {
  salary_below_expected: 'зарплата ниже ожиданий',
  no_offer_detail: 'не хватает деталей в оффере',
  timing: 'не подходит по срокам',
  other: 'другое',
}

/** FE-17: Need Health — decline analytics by reason. */
export function HealthPanel({ health }: { health: NeedHealth }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <header className="text-sm font-semibold">Здоровье потребности</header>

      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col gap-0.5 rounded-lg border border-border p-2">
          <span className="text-lg font-bold tabular-nums">{health.active}</span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Activity className="h-3 w-3" /> в работе
          </span>
        </div>
        <div className="flex flex-col gap-0.5 rounded-lg border border-border p-2">
          <span className="text-lg font-bold tabular-nums">{health.declined_last_30d}</span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <CircleOff className="h-3 w-3" /> отказов (30 дней)
          </span>
        </div>
        <div className="flex flex-col gap-0.5 rounded-lg border border-border p-2">
          <span className="text-lg font-bold tabular-nums">
            {Math.round(health.acceptance_rate * 100)}%
          </span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Percent className="h-3 w-3" /> принятия
          </span>
        </div>
      </div>

      <ul className="flex flex-col gap-2">
        {health.by_reason.map((byReason) => (
          <li key={byReason.reason} className="flex flex-col gap-1">
            <span className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{REASON_LABEL[byReason.reason] ?? byReason.reason}</span>
              <span className="tabular-nums text-foreground">
                {byReason.count} · {Math.round(byReason.share * 100)}%
              </span>
            </span>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-warn"
                style={{ width: `${Math.round(byReason.share * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}