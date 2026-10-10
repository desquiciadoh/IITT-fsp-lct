/**
 * FE-10 · Scouting filters panel.
 *
 * Every control writes straight into the URL via `useScoutingUrlState` —
 * the URL is the single source of truth (FE2.md §FE-10). When the backend
 * ignores filters (gap G8, no `facets` in the pool response) the header
 * shows a "client-side" badge so the employer knows pagination counts are
 * approximate.
 */
import { X } from 'lucide-react'

import type { FspFilter, Grade, LeagueShelf, ScoutingFilters, WorkFormat } from '@/api/types'
import { GRADE_LABEL, SPEC_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'
import { DEFAULT_FILTERS } from '@/features/scouting/url-state'
import { cn } from '@/lib/utils'

const GRADES: Grade[] = ['intern', 'junior', 'middle', 'senior']
const FORMATS: WorkFormat[] = ['office', 'hybrid', 'remote']
const FSP_OPTIONS: { value: FspFilter; label: string }[] = [
  { value: 'any', label: 'Любой' },
  { value: 'linked', label: 'Привязан ФСП' },
  { value: 'prize', label: 'Призёр ФСП' },
]

export const PRESET_LABEL: Record<string, string> = {
  'verified-only': 'Только подтверждённые',
  fsp: 'С ФСП',
}

function toggleIn<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value]
}

export function FiltersBar({
  filters,
  setFilters,
  resetFilters,
  shelves,
  clientFiltered,
}: {
  filters: ScoutingFilters
  setFilters: (next: Partial<ScoutingFilters>) => void
  resetFilters: () => void
  shelves?: LeagueShelf[]
  /** true when the pool was filtered in the browser (fallback, gap G8) */
  clientFiltered?: boolean
}) {
  const activePreset = filters.preset ? PRESET_LABEL[filters.preset] ?? filters.preset : null

  const applyPreset = (key: string) => {
    if (filters.preset === key) {
      setFilters({ preset: undefined, confirmed_only: false, fsp: 'any' })
      return
    }
    if (key === 'verified-only') {
      setFilters({ preset: key, confirmed_only: true })
    } else if (key === 'fsp') {
      setFilters({ preset: key, fsp: 'linked' })
    }
  }

  const shelfFor = (g: Grade) => shelves?.find((sh) => sh.grade === g)

  return (
    <section
      aria-label="Фильтры кандидатов"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Фильтры</h2>
        <div className="flex items-center gap-2">
          {clientFiltered && (
            <span
              className="rounded-full border border-dashed border-muted-foreground/60 px-2 py-0.5 text-[10px] uppercase text-muted-foreground"
              title="Бэкенд ещё не применяет фильтры на сервере (G8) — применили в браузере"
            >
              фильтр в браузере
            </span>
          )}
          {!isDefault(filters) && (
            <button
              type="button"
              onClick={resetFilters}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              <X className="h-3 w-3" /> Сбросить
            </button>
          )}
        </div>
      </div>

      {/* presets */}
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(PRESET_LABEL).map(([key, label]) => (
          <Chip
            key={key}
            active={filters.preset === key}
            onClick={() => applyPreset(key)}
            label={label}
          />
        ))}
        {activePreset && (
          <span className="self-center text-xs text-muted-foreground">пресет: {activePreset}</span>
        )}
      </div>

      <FilterRow label="Грейд">
        {GRADES.map((g) => (
          <Chip
            key={g}
            active={filters.grades.includes(g)}
            onClick={() => setFilters({ grades: toggleIn(filters.grades, g), preset: undefined })}
            label={GRADE_LABEL[g] ?? g}
            count={(() => { const sh = shelfFor(g); return sh ? sh.confirmed + sh.unconfirmed : undefined })()}
          />
        ))}
      </FilterRow>

      <FilterRow label="Формат">
        {FORMATS.map((f) => (
          <Chip
            key={f}
            active={filters.formats.includes(f)}
            onClick={() => setFilters({ formats: toggleIn(filters.formats, f) })}
            label={WORK_FORMAT_LABEL[f] ?? f}
          />
        ))}
      </FilterRow>

      <FilterRow label="ФСП">
        {FSP_OPTIONS.map((o) => (
          <Chip
            key={o.value}
            active={filters.fsp === o.value}
            onClick={() => setFilters({ fsp: o.value, preset: o.value === 'any' ? undefined : filters.preset })}
            label={o.label}
          />
        ))}
      </FilterRow>

      <FilterRow label="Навыки">
        {['python', 'django', 'fastapi', 'postgresql', 'redis', 'kafka'].map((s) => (
          <Chip
            key={s}
            active={filters.skills.includes(s)}
            onClick={() => setFilters({ skills: toggleIn(filters.skills, s) })}
            label={s}
          />
        ))}
      </FilterRow>

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.confirmed_only}
            onChange={(e) =>
              setFilters({
                confirmed_only: e.target.checked,
                preset: e.target.checked ? filters.preset : undefined,
              })
            }
            className="h-4 w-4 accent-[var(--fsp-accent)]"
          />
          Только подтверждённая лига
        </label>

        <label className="flex items-center gap-2 text-sm">
          Зарплата до
          <input
            type="number"
            min={0}
            step={10000}
            value={filters.salary_max ?? ''}
            placeholder="—"
            onChange={(e) => {
              const v = e.target.value
              setFilters(v === '' ? { salary_max: undefined } : { salary_max: Number(v) })
            }}
            className="w-28 rounded-md border border-border bg-background px-2 py-1 text-sm tabular-nums"
          />
          ₽
        </label>
      </div>
    </section>
  )
}

function isDefault(f: ScoutingFilters): boolean {
  return (
    f.grades.length === 0 &&
    f.skills.length === 0 &&
    f.formats.length === 0 &&
    f.fsp === DEFAULT_FILTERS.fsp &&
    !f.confirmed_only &&
    f.salary_max === undefined &&
    !f.preset
  )
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-16 shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      {children}
    </div>
  )
}

function Chip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean
  onClick: () => void
  label: string
  count?: number
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-full border px-2.5 py-1 text-xs transition-colors',
        active
          ? 'border-[var(--fsp-accent)] bg-[var(--fsp-accent)]/10 font-semibold text-[var(--fsp-accent)]'
          : 'border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground',
      )}
    >
      {label}
      {count !== undefined && <span className="ml-1 tabular-nums opacity-60">{count}</span>}
    </button>
  )
}

/** Small helper reused by the page header for spec labels. */
export const specLabel = (spec?: string) => (spec ? SPEC_LABEL[spec] ?? spec : '')
