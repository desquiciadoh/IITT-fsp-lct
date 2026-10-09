import { SlidersHorizontal } from 'lucide-react'
import { PRESETS, PRESET_ORDER, SCORE_KEYS, normalizeWeights } from '@/features/pool/rank'
import type { PoolWeights, WeightPreset } from '@/api/types'

const KEY_LABEL: Record<(typeof SCORE_KEYS)[number], string> = {
  skill: 'скиллы',
  strength: 'профиль',
  grade: 'грейд',
  salary: 'зарплата',
  semantic: 'семантика',
  freshness: 'свежесть',
  fsp: 'ФСП',
}

const PRESET_LABEL: Record<WeightPreset, string> = {
  balanced: 'Сбалансировано',
  skills: 'Скиллы',
  budget: 'Бюджет',
}

/** FE-17 weight panel: presets + live sliders that re-rank without a request. */
export function WeightPanel({
  weights,
  onChange,
}: {
  weights: PoolWeights
  onChange: (weights: PoolWeights) => void
}) {
  const setWeight = (key: (typeof SCORE_KEYS)[number], value: number) => {
    onChange(normalizeWeights({ ...weights, [key]: value }))
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <header className="flex items-center gap-1.5 text-sm font-semibold">
        <SlidersHorizontal className="h-4 w-4" /> Веса матчинга
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          ре-ранк без запроса к серверу
        </span>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {PRESET_ORDER.map((preset) => (
          <button
            key={preset}
            onClick={() => onChange({ ...PRESETS[preset] })}
            className="rounded-md border border-border px-2.5 py-1 text-xs transition-colors hover:border-primary data-[active=true]:border-primary data-[active=true]:bg-primary/10 data-[active=true]:text-foreground"
            data-active={String(JSON.stringify(weights) === JSON.stringify(PRESETS[preset]))}
          >
            {PRESET_LABEL[preset]}
          </button>
        ))}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {SCORE_KEYS.map((key) => {
          const value = Math.round((weights[key] ?? 0) * 100)
          return (
            <label key={key} className="flex flex-col gap-1 text-xs text-muted-foreground">
              <span className="flex items-center justify-between">
                <span className="uppercase tracking-wide">{KEY_LABEL[key]}</span>
                <span className="tabular-nums">{value}%</span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={value}
                aria-label={`Вес компонента ${KEY_LABEL[key]}`}
                onChange={(e) => setWeight(key, Number(e.target.value) / 100)}
                className="w-full accent-[var(--fsp-accent)]"
              />
            </label>
          )
        })}
      </div>
    </div>
  )
}