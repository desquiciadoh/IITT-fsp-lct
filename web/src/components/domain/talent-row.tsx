import { AlertTriangle, Star, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { LeagueBadge, type Grade, type LeagueStatus, type Spec } from '@/components/domain/league-badge'
import { SalaryTag } from '@/components/domain/salary-tag'
import { ReasonChips } from '@/components/domain/reason-chips'
import { WORK_FORMAT_LABEL } from '@/lib/labels'
import type { PoolSkill, Reason, TalentShortView } from '@/api/types'

export type TalentRowProps = {
  talent: TalentShortView
  score?: number
  reasons?: Reason[]
  /** gap G8 target — explicit weakness list; derived from minus-reasons until BE serves it */
  gaps?: string[]
  shortlisted?: boolean
  onToggleShortlist?: (publicId: string) => void
  className?: string
}

export function TalentRow({
  talent,
  score,
  reasons = [],
  gaps,
  shortlisted = false,
  onToggleShortlist,
  className,
}: TalentRowProps) {
  const name = talent.display_name ?? talent.public_id
  const league = talent.league
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-4 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:bg-secondary',
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold">{name}</span>
          <span className="font-mono text-xs text-muted-foreground">{talent.public_id}</span>
          {talent.fsp?.linked && (
            <span
              className="inline-flex items-center gap-1 text-xs text-warn"
              title={talent.fsp.best_tier ? `лучший результат: ${talent.fsp.best_tier}` : 'ФСП подключён'}
            >
              <Trophy className="h-3.5 w-3.5" />
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {league && (
            <LeagueBadge
              status={league.status as LeagueStatus}
              grade={league.grade as Grade}
              spec={league.specialization as Spec}
            />
          )}
          {talent.city && <span className="text-xs text-muted-foreground">{talent.city}</span>}
          {(talent.work_formats ?? []).map((f) => (
            <span key={f} className="text-xs text-muted-foreground">
              · {WORK_FORMAT_LABEL[f] ?? f}
            </span>
          ))}
        </div>
        {reasons.length > 0 && <ReasonChips reasons={reasons} />}
        {/* gaps (weaknesses) — derived from minus-reasons until BE serves them (G8) */}
        {(gaps?.length ?? 0) > 0 && (
          <ul className="flex flex-col gap-1" aria-label="Зоны роста">
            {gaps!.map((g, i) => (
              <li key={i} className="flex items-center gap-1.5 text-xs text-warn">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
                {g}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <SalaryTag
          min={talent.salary_min ?? 0}
          max={talent.salary_max ?? 0}
          type={talent.salary_type || 'gross'}
        />
        <div className="flex items-center gap-2">
          {score !== undefined && (
            <span className="text-xs font-bold tabular-nums text-primary">{Math.round(score)}</span>
          )}
          {onToggleShortlist && (
            <button
              type="button"
              aria-pressed={shortlisted}
              aria-label={shortlisted ? 'Убрать из избранного' : 'В избранное'}
              onClick={(e) => {
                // keep row-level click handlers (drawer) from firing on star toggle
                e.stopPropagation()
                onToggleShortlist(talent.public_id)
              }}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:text-primary"
            >
              <Star
                className={cn('h-4 w-4', shortlisted && 'fill-current text-primary')}
              />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
