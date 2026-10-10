import { useState } from 'react'
import { X } from 'lucide-react'
import type { Grade, PoolFilters, WorkFormat } from '@/api/types'
import { useTaxonomy } from '@/api/profile'
import { activeFilterCount, EMPTY_FILTERS } from '@/features/scouting/filters'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GRADE_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'
import { cn } from '@/lib/utils'

/**
 * FE-10 · Pool filter panel. Every change goes through `onChange` → URL query
 * string (single source of truth); the panel itself is stateless except for
 * the salary input draft. Facet counts appear only when the backend ships
 * them (gap G8) — capability detection, not hardcoding.
 */

const GRADES: Grade[] = ['intern', 'junior', 'middle', 'senior']
const FORMATS: WorkFormat[] = ['office', 'hybrid', 'remote']
const FSP_OPTIONS = [
  { value: 'any', label: 'ФСП: не важно' },
  { value: 'linked', label: 'привязан' },
  { value: 'prize', label: 'призёр' },
] as const

export function FilterPanel({
  filters,
  onChange,
  facets,
}: {
  filters: PoolFilters
  onChange: (next: Partial<PoolFilters>) => void
  facets?: Record<string, Record<string, number>>
}) {
  const { data: taxonomy } = useTaxonomy()
  const [salaryDraft, setSalaryDraft] = useState(
    filters.salary_max != null ? String(filters.salary_max) : '',
  )

  const toggleIn = <T extends string>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((x) => x !== value) : [...list, value]

  const commitSalary = () => {
    const n = Number(salaryDraft.replace(/\s/g, ''))
    onChange({ salary_max: salaryDraft.trim() && Number.isFinite(n) && n > 0 ? n : null })
  }

  const skillSuggestions = (taxonomy?.skills ?? []).filter(
    (s) => !filters.skills.includes(s),
  )

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3">
      {/* Presets */}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Пресеты фильтров">
        <PresetChip
          active={filters.preset === 'fsp_stars'}
          label="⭐ Звёзды ФСП"
          onClick={() => onChange({ preset: filters.preset === 'fsp_stars' ? null : 'fsp_stars' })}
        />
        <PresetChip
          active={filters.preset === 'confirmed'}
          label="Только подтверждённые"
          onClick={() => onChange({ preset: filters.preset === 'confirmed' ? null : 'confirmed' })}
        />
      </div>

      {/* Grades */}
      <fieldset className="flex flex-wrap items-center gap-1.5">
        <legend className="sr-only">Грейды</legend>
        <span className="mr-1 text-xs font-semibold uppercase text-muted-foreground">Грейд</span>
        {GRADES.map((g) => (
          <PresetChip
            key={g}
            active={filters.grades.includes(g)}
            label={`${GRADE_LABEL[g]}${facets?.grades?.[g] != null ? ` (${facets.grades[g]})` : ''}`}
            onClick={() => onChange({ grades: toggleIn(filters.grades, g) })}
          />
        ))}
      </fieldset>

      {/* FSP + confirmed_only */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5" role="group" aria-label="ФСП">
          {FSP_OPTIONS.map((o) => (
            <PresetChip
              key={o.value}
              active={filters.fsp === o.value}
              label={o.label}
              onClick={() => onChange({ fsp: o.value })}
            />
          ))}
        </div>
        <label className="ml-auto flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-[var(--fsp-accent)]"
            checked={filters.confirmed_only}
            onChange={(e) => onChange({ confirmed_only: e.target.checked })}
          />
          только подтверждённый грейд
        </label>
      </div>

      {/* Formats */}
      <fieldset className="flex flex-wrap items-center gap-1.5">
        <legend className="sr-only">Формат работы</legend>
        <span className="mr-1 text-xs font-semibold uppercase text-muted-foreground">Формат</span>
        {FORMATS.map((f) => (
          <PresetChip
            key={f}
            active={filters.formats.includes(f)}
            label={WORK_FORMAT_LABEL[f]}
            onClick={() => onChange({ formats: toggleIn(filters.formats, f) })}
          />
        ))}
      </fieldset>

      {/* Salary max */}
      <div className="flex items-center gap-2">
        <label htmlFor="salary-max" className="text-xs font-semibold uppercase text-muted-foreground">
          Зарплата до, ₽
        </label>
        <Input
          id="salary-max"
          inputMode="numeric"
          className="w-36"
          placeholder="напр. 300000"
          value={salaryDraft}
          onChange={(e) => setSalaryDraft(e.target.value)}
          onBlur={commitSalary}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitSalary()
          }}
        />
      </div>

      {/* Skills */}
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase text-muted-foreground">Навыки</span>
        {filters.skills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {filters.skills.map((s) => (
              <button
                key={s}
                type="button"
                className="inline-flex items-center gap-1 rounded-full border border-primary/50 bg-primary/10 px-2 py-0.5 text-xs"
                onClick={() => onChange({ skills: filters.skills.filter((x) => x !== s) })}
                aria-label={`Убрать навык ${s}`}
              >
                {s}
                <X className="h-3 w-3" />
              </button>
            ))}
          </div>
        )}
        {skillSuggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {skillSuggestions.slice(0, 8).map((s) => (
              <button
                key={s}
                type="button"
                className="rounded-full border border-dashed border-muted-foreground/60 px-2 py-0.5 text-xs text-muted-foreground hover:border-solid hover:text-foreground"
                onClick={() => onChange({ skills: [...filters.skills, s] })}
              >
                + {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {activeFilterCount(filters) > 0 && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onChange({ ...EMPTY_FILTERS })}>
            Сбросить фильтры
          </Button>
        </div>
      )}
    </div>
  )
}

function PresetChip({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-full border px-2.5 py-1 text-xs transition-colors',
        active
          ? 'border-primary bg-primary/15 font-semibold text-primary'
          : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}
