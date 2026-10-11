import { Activity, AlertTriangle } from 'lucide-react'
import { usePositionHealth } from '@/api/scouting'
import type { PositionHealth } from '@/api/types'
import { DECLINE_REASON_LABEL } from '@/lib/labels'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'

const HEALTH_VARIANT: Record<PositionHealth['health_status'], 'success' | 'warning' | 'danger'> = {
  good: 'success',
  needs_attention: 'warning',
  critical: 'danger',
}

function percent(fraction: number | undefined | null): string {
  if (fraction == null) return '0%'
  return `${Math.round(fraction * 100)}%`
}

export function NeedHealthPanel({ positionId, className }: { positionId: string; className?: string }) {
  const { data, isLoading, isError, refetch } = usePositionHealth(positionId)

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5 text-base">
          <Activity className="h-4 w-4" /> Need Health
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError ? (
          <ErrorState onRetry={() => void refetch()} />
        ) : data && data.total_offers > 0 ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={HEALTH_VARIANT[data.health_status]}>
                {data.health_status === 'good'
                  ? 'ок'
                  : data.health_status === 'needs_attention'
                    ? 'требует внимания'
                    : 'критично'}
              </Badge>
              <span className="text-xs text-muted-foreground">
                офферов: {data.total_offers} · принято {data.accepted_offers} / отказы{' '}
                {data.declined_offers} / истекло {data.expired_offers}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-muted/50 px-3 py-2">
                <span className="block text-xs text-muted-foreground">Acceptance rate</span>
                <span className="text-lg font-bold tabular-nums">{percent(data.acceptance_rate)}</span>
              </div>
              <div className="rounded-lg bg-muted/50 px-3 py-2">
                <span className="block text-xs text-muted-foreground">Decline rate</span>
                <span className="text-lg font-bold tabular-nums">{percent(data.decline_rate)}</span>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">Причины отказов</span>
              {data.top_decline_reason && (
                <p className="flex items-center gap-1 text-xs text-warn">
                  <AlertTriangle className="h-3 w-3" />
                  Чаще всего: {DECLINE_REASON_LABEL[data.top_decline_reason] ?? data.top_decline_reason}
                </p>
              )}
              <ReasonBars reasons={data.decline_reasons} />
            </div>

            <p className="text-sm text-muted-foreground">{data.diagnosis}</p>

            <p className="text-xs text-muted-foreground">
              Кредиты outreach на неделю:{' '}
              <span className="font-semibold tabular-nums">{data.weekly_credits_remaining}</span>
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Пока нет отправленных офферов — начните подбор, чтобы увидеть аналитику воронки.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function ReasonBars({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons)
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">Отказов по причинам нет.</p>
  }
  const max = Math.max(...entries.map((e) => e.count))
  return (
    <div className="flex flex-col gap-1">
      {entries.map(({ reason, count }) => (
        <div key={reason} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 truncate text-muted-foreground">
            {DECLINE_REASON_LABEL[reason] ?? reason}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full"
              style={{ width: `${(count / max) * 100}%`, backgroundColor: 'var(--fsp-info)' }}
            />
          </div>
          <span className="w-5 text-right tabular-nums">{count}</span>
        </div>
      ))}
    </div>
  )
}