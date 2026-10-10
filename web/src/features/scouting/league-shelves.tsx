import { useLeagues } from '@/api/scouting'
import type { LeagueShelf, Spec } from '@/api/types'
import { summarizeShelves } from '@/features/scouting/filters'
import { Skeleton } from '@/components/ui/skeleton'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * FE-10 · League shelves (gap G7).
 * GET /api/leagues?specialization= → [{specialization, grade, confirmed,
 * unconfirmed, median_expectation?}]. Rendered as compact stat tiles; the
 * component tolerates both a plain array and an {items} envelope upstream.
 */
export function LeagueShelves({ specialization }: { specialization?: Spec }) {
  const { data, isLoading, isError } = useLeagues(specialization)

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    )
  }
  if (isError || !data || data.length === 0) return null

  const totals = summarizeShelves(data)

  return (
    <section aria-label="Лиги" className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {data.map((shelf) => (
          <ShelfCard key={`${shelf.specialization}-${shelf.grade}`} shelf={shelf} />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Всего в лиге «{SPEC_LABEL[specialization ?? data[0]?.specialization ?? ''] ?? specialization}»:{' '}
        {totals.confirmed} подтверждённых, {totals.unconfirmed} неподтверждённых
        {totals.median != null && <> · медиана ожиданий {formatMoney(totals.median)} ₽</>}
      </p>
    </section>
  )
}

function ShelfCard({ shelf }: { shelf: LeagueShelf }) {
  const total = shelf.confirmed + shelf.unconfirmed
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-card px-3 py-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {GRADE_LABEL[shelf.grade] ?? shelf.grade}
      </span>
      <span className={cn('text-lg font-bold tabular-nums', total === 0 && 'text-muted-foreground')}>
        {total}
      </span>
      <span className="text-xs text-muted-foreground">
        {shelf.confirmed} подтв. · {shelf.unconfirmed} не подтв.
      </span>
      {shelf.median_expectation != null && (
        <span className="text-xs text-muted-foreground">
          медиана {formatMoney(shelf.median_expectation)} ₽
        </span>
      )}
    </div>
  )
}
