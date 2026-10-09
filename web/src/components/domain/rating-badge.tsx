import { cn } from '@/lib/utils'

export function RatingBadge({
  rating,
  ci,
  percentile,
  className,
}: {
  rating: number
  ci?: number
  percentile?: number
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-baseline gap-2', className)}>
      <span className="text-2xl font-extrabold tabular-nums">{rating}</span>
      {ci !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums">± {ci}</span>
      )}
      {percentile !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums">
          {percentile}-й перцентиль
        </span>
      )}
    </span>
  )
}
