import type { TwinDifficultyProfile } from '@/api/types'

const AXES: { key: keyof TwinDifficultyProfile; label: string; color: string }[] = [
  { key: 'skill', label: 'Скиллы', color: 'var(--fsp-accent)' },
  { key: 'grade', label: 'Грейд', color: 'var(--fsp-warn)' },
  { key: 'strength', label: 'Профиль', color: 'var(--fsp-info)' },
]

/** FE-14: difficulty profile as three 0–100 bars (blueprint vs instances side by side). */
export function DifficultyBars({ profile }: { profile: TwinDifficultyProfile }) {
  return (
    <div aria-label="Профиль сложности" className="flex flex-col gap-1.5">
      {AXES.map((axis) => {
        const value = Math.round(profile[axis.key])
        return (
          <div key={axis.key} className="flex items-center gap-2 text-xs">
            <span className="w-14 shrink-0 text-muted-foreground">{axis.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" role="presentation">
              <div
                className="h-full rounded-full"
                style={{ width: `${value}%`, backgroundColor: axis.color }}
              />
            </div>
            <span className="w-8 shrink-0 text-right tabular-nums text-muted-foreground">{value}</span>
          </div>
        )
      })}
    </div>
  )
}