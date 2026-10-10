import type { JdBlueprintItem } from '@/api/types'

/** Topic-weight bars from the JD parser (FE-09 wizard, step 3). */
export function BlueprintBars({ items }: { items: JdBlueprintItem[] }) {
  if (items.length === 0) return null
  const max = Math.max(...items.map((i) => i.weight))
  return (
    <div className="flex flex-col gap-1.5" role="img" aria-label="Профиль компетенций вакансии">
      {items.map((item) => (
        <div key={item.topic} className="flex items-center gap-2 text-xs">
          <span className="w-40 truncate text-muted-foreground">{item.topic}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.round((item.weight / max) * 100)}%` }}
            />
          </div>
          <span className="w-10 text-right tabular-nums text-muted-foreground">
            {Math.round(item.weight * 100)}%
          </span>
        </div>
      ))}
    </div>
  )
}
