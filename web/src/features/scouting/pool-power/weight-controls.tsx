import { RANK_AXES, RANK_AXIS_LABEL, PRESETS, type RankAxis, type WeightProfile } from '@/features/scouting/pool-power/ranking'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * FE-17 · Weight presets + sliders that re-rank the pool live (no request).
 * Local state only — the ranking derives from the already-loaded items.
 */
export function WeightControls({
  weights,
  onChange,
}: {
  weights: WeightProfile
  onChange: (next: WeightProfile) => void
}) {
  const setAxis = (axis: RankAxis, value: number) => onChange({ ...weights, [axis]: value })

  return (
    <section
      aria-label="Веса скоринга"
      className="rounded-xl border border-border bg-card p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">Веса скоринга</h3>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Пресеты весов">
          {PRESETS.map((p) => {
            const active = RANK_AXES.every((a) => weights[a] === p.weights[a])
            return (
              <button
                key={p.key}
                type="button"
                title={p.description}
                aria-pressed={active}
                onClick={() => onChange({ ...p.weights })}
                className={cn(
                  'rounded-full border border-border px-3 py-1 text-xs transition-colors',
                  active ? 'bg-primary text-primary-foreground' : 'text-foreground hover:border-primary/50',
                )}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2">
        {RANK_AXES.map((axis) => (
          <label key={axis} className="flex flex-col gap-1 text-sm">
            <span className="flex items-center justify-between text-xs text-muted-foreground">
              {RANK_AXIS_LABEL[axis]}
              <span className="tabular-nums">{weights[axis].toFixed(1)}</span>
            </span>
            <input
              type="range"
              min={0}
              max={3}
              step={0.5}
              value={weights[axis]}
              onChange={(e) => setAxis(axis, Number(e.target.value))}
              aria-label={`Вес: ${RANK_AXIS_LABEL[axis]}`}
              className="w-full accent-[var(--fsp-accent)]"
            />
          </label>
        ))}
      </div>

      <div className="mt-2 flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange({ ...PRESETS[0].weights })}
        >
          Сбросить
        </Button>
      </div>
    </section>
  )
}