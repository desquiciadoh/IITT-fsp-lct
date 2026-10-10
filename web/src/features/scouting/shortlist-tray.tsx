/**
 * FE-10 · Shortlist tray (лоток).
 *
 * Lives OUTSIDE the filtered list: built from `shortlisted: true` items
 * across every cached pool query of this position, so toggling filters never
 * empties the tray (FE2.md §FE-10 "tray survives filters"). The tray is
 * collapsible and sticky at the bottom on narrow screens.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Star, X } from 'lucide-react'

import { keys } from '@/api/keys'
import type { PoolItemView, ScoutingPoolResponse } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * Collect shortlisted items from all cached pool queries of one position
 * (gap G16 — no "list shortlist" endpoint). Called during render, so every
 * optimistic patch / refetch of any pool page is reflected immediately and
 * the tray survives filter changes. Deduped by public_id, score-desc.
 */
export function collectShortlist(
  positionId: string,
  qc: ReturnType<typeof useQueryClient>,
): PoolItemView[] {
  const all = qc.getQueriesData<ScoutingPoolResponse>({ queryKey: keys.pool(positionId) })
  const byId = new Map<string, PoolItemView>()
  for (const [, data] of all) {
    for (const item of data?.items ?? []) {
      if (item.shortlisted && !byId.has(item.talent.public_id)) {
        byId.set(item.talent.public_id, item)
      }
    }
  }
  return [...byId.values()].sort((a, b) => b.score - a.score)
}

export function ShortlistTray({
  items,
  onOpenCandidate,
  onRemove,
}: {
  items: PoolItemView[]
  onOpenCandidate: (publicId: string) => void
  onRemove: (publicId: string) => void
}) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside
      aria-label="Лоток избранного"
      className={cn(
        'sticky bottom-0 z-20 rounded-xl border border-border bg-card shadow-lg',
        collapsed && 'shadow-none',
      )}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left"
        aria-expanded={!collapsed}
      >
        <span className="inline-flex items-center gap-2 text-sm font-semibold">
          <Star className="h-4 w-4 fill-current text-primary" />
          В избранном
          <span className="rounded-full bg-[var(--fsp-accent)]/15 px-2 py-0.5 text-xs tabular-nums text-[var(--fsp-accent)]">
            {items.length}
          </span>
        </span>
        {collapsed ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {!collapsed && (
        <div className="max-h-56 overflow-y-auto border-t border-border px-3 py-2">
          {items.length === 0 ? (
            <p className="px-1 py-3 text-sm text-muted-foreground">
              Пусто. Отмечайте кандидатов звёздочкой в списке — лоток не пропадает при смене
              фильтров.
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {items.map((item) => {
                const name = item.talent.display_name ?? item.talent.public_id
                return (
                  <li
                    key={item.talent.public_id}
                    className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenCandidate(item.talent.public_id)}
                      className="min-w-0 text-left text-sm"
                    >
                      <span className="font-medium">{name}</span>
                      <span className="ml-2 text-xs tabular-nums text-primary">
                        {Math.round(item.score)}
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={`Убрать ${name} из избранного`}
                      onClick={() => onRemove(item.talent.public_id)}
                      className="rounded-md p-1 text-muted-foreground hover:text-destructive"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </aside>
  )
}
