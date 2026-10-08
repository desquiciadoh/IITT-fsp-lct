import { Link2, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SPORTS_RANK_LABEL, PLACEMENT_TIER_LABEL } from '@/lib/labels'

export type SportsRank = 'cat3' | 'cat2' | 'cat1' | 'kms' | 'ms'
export type PlacementTier = 'winner' | 'prize_winner' | 'finalist' | 'participant'

/** FSP (sports passport) trust chip: linked/unlinked + best result. */
export function FspBadge({
  linked,
  rank,
  bestTier,
  results,
  className,
}: {
  linked: boolean
  rank?: SportsRank
  bestTier?: PlacementTier
  results?: number
  className?: string
}) {
  if (!linked) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground',
          className,
        )}
        title="ФСП не привязан"
      >
        <Link2 className="h-3 w-3" />
        нет ФСП
      </span>
    )
  }
  const parts = [
    rank && SPORTS_RANK_LABEL[rank],
    bestTier && PLACEMENT_TIER_LABEL[bestTier],
  ].filter(Boolean)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-xs font-medium text-warn',
        className,
      )}
      title={results ? `результатов: ${results}` : 'ФСП привязан'}
    >
      <Trophy className="h-3 w-3" />
      {parts.length > 0 ? parts.join(' · ') : 'ФСП'}
    </span>
  )
}
