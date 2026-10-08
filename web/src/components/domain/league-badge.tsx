import { cn } from '@/lib/utils'

export type LeagueStatus = 'pending' | 'confirmed' | 'unconfirmed'
export type Grade = 'intern' | 'junior' | 'middle' | 'senior'
export type Spec = 'backend' | 'frontend' | 'ml_data'

const STATUS_COLOR: Record<LeagueStatus, string> = {
  pending: 'text-muted-foreground border-border',
  confirmed: 'text-[var(--fsp-league-confirmed)] border-[var(--fsp-league-confirmed)]/40',
  unconfirmed: 'text-[var(--fsp-league-unconfirmed)] border-[var(--fsp-league-unconfirmed)]/40',
}

const STATUS_LABEL: Record<LeagueStatus, string> = {
  pending: 'ожидает',
  confirmed: 'подтверждён',
  unconfirmed: 'неподтверждён',
}

const GRADE_LABEL: Record<Grade, string> = {
  intern: 'стажёр',
  junior: 'джун',
  middle: 'мидл',
  senior: 'синьор',
}

const SPEC_LABEL: Record<Spec, string> = {
  backend: 'бэкенд',
  frontend: 'фронтенд',
  ml_data: 'ml/data',
}

export function LeagueBadge({
  status,
  grade,
  spec,
  className,
}: {
  status: LeagueStatus
  grade: Grade
  spec?: Spec
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold',
        STATUS_COLOR[status],
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {spec ? `${SPEC_LABEL[spec]} · ` : ''}
      {GRADE_LABEL[grade]} · {STATUS_LABEL[status]}
    </span>
  )
}
