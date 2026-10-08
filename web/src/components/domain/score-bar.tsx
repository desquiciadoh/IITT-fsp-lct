import { cn } from '@/lib/utils'
import { normalizeComponents } from '@/components/domain/normalize'
import type { ScoreComponent, ScoreComponentsDict } from '@/api/types'

const SEGMENT_COLOR: Record<ScoreComponent['key'], string> = {
  skill: 'var(--fsp-accent)',
  strength: 'var(--fsp-info)',
  grade: 'var(--fsp-warn)',
  salary: '#a78bfa',
  semantic: '#f472b6',
  freshness: 'var(--fsp-muted)',
  fsp: '#ffc857',
}

const SEGMENT_LABEL: Record<ScoreComponent['key'], string> = {
  skill: 'скиллы',
  strength: 'профиль',
  grade: 'грейд',
  salary: 'зарплата',
  semantic: 'семантика',
  freshness: 'свежесть',
  fsp: 'ФСП',
}

export function ScoreBar({
  score,
  components,
  className,
}: {
  score: number
  components: ScoreComponent[] | ScoreComponentsDict
  className?: string
}) {
  const normalized = normalizeComponents(components)
  const total =
    normalized.reduce((sum, c) => sum + Math.max(0, c.contribution), 0) || 1
  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold tabular-nums">{Math.round(score)} / 100</span>
        <span className="text-muted-foreground">{normalized.length} компонентов</span>
      </div>
      <div className="mt-1 flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {normalized.map((c) => (
          <div
            key={c.key}
            title={`${SEGMENT_LABEL[c.key]}: ${c.contribution.toFixed(1)}${c.weight !== undefined ? ` (вес ${(c.weight * 100).toFixed(0)}%)` : ''}`}
            style={{
              width: `${(Math.max(0, c.contribution) / total) * 100}%`,
              backgroundColor: SEGMENT_COLOR[c.key],
            }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {normalized.map((c) => (
          <span key={c.key} className="inline-flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: SEGMENT_COLOR[c.key] }}
            />
            {SEGMENT_LABEL[c.key]}
          </span>
        ))}
      </div>
    </div>
  )
}
