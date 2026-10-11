import { Star } from 'lucide-react'
import type { TalentShort } from '@/api/types'
import { LeagueBadge, type Grade, type LeagueStatus, type Spec } from '@/components/domain/league-badge'
import { SalaryTag } from '@/components/domain/salary-tag'

/**
 * FE-10 · Shortlist tray. Built from `shortlisted: true` pool items (gap G16 —
 * no list endpoint on the real BE yet); the cache lives in TanStack Query and
 * survives filter changes. Clicking a row opens the candidate drawer (?c=…).
 */
export function ShortlistTray({
  talents,
  onSelect,
  onRemove,
}: {
  talents: TalentShort[]
  onSelect: (publicId: string) => void
  onRemove: (publicId: string) => void
}) {
  return (
    <aside
      aria-label="Шорт-лист"
      className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3"
    >
      <div className="flex items-center gap-2">
        <Star className="h-4 w-4 fill-current text-primary" />
        <h2 className="text-sm font-semibold">Шорт-лист</h2>
        <span className="ml-auto rounded-full bg-primary/15 px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--fsp-accent-strong)]">
          {talents.length}
        </span>
      </div>

      {talents.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Отмечайте кандидатов звёздочкой — они останутся здесь даже при смене фильтров.
        </p>
      ) : (
        <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto">
          {talents.map((t) => (
            <li key={t.public_id}>
              <div className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary">
                <button
                  type="button"
                  className="flex min-w-0 flex-1 flex-col items-start text-left"
                  onClick={() => onSelect(t.public_id)}
                >
                  <span className="truncate text-sm font-medium">
                    {t.display_name ?? t.public_id}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {t.league && (
                      <LeagueBadge
                        status={t.league.status as LeagueStatus}
                        grade={t.league.grade as Grade}
                        spec={t.league.specialization as Spec}
                        className="text-[10px]"
                      />
                    )}
                    {(t.salary_min != null || t.salary_max != null) && (
                      <SalaryTag
                        min={t.salary_min ?? 0}
                        max={t.salary_max ?? 0}
                        type={t.salary_type || 'gross'}
                      />
                    )}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Убрать ${t.display_name ?? t.public_id} из шорт-листа`}
                  className="rounded-md p-1 text-primary opacity-70 transition-opacity hover:opacity-100"
                  onClick={() => onRemove(t.public_id)}
                >
                  <Star className="size-4 fill-current" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
