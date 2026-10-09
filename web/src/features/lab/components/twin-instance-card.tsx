import { ShieldAlert, Timer } from 'lucide-react'
import { DifficultyBars } from '@/features/lab/components/difficulty-bars'
import type { TwinInstance } from '@/api/types'

/** FE-14: one of two generated instances — renders only ItemView-visible fields. */
export function TwinInstanceCard({ instance }: { instance: TwinInstance }) {
  return (
    <article className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <header className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">{instance.id}</span>
        {instance.status === 'ready' ? (
          <span className="rounded-md border border-plus/40 bg-plus/10 px-2 py-0.5 text-xs text-plus">
            готова к прогону
          </span>
        ) : (
          <span className="rounded-md border border-warn/40 bg-warn/10 px-2 py-0.5 text-xs text-warn">
            черновик
          </span>
        )}
      </header>

      <DifficultyBars profile={instance.difficulty} />

      <ol className="flex flex-col gap-2 border-t border-border pt-3">
        {instance.items.map((item) => (
          <li key={item.seq} className="flex flex-col gap-1 rounded-lg border border-border bg-background p-3">
            <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
              <span className="font-mono">#{String(item.seq).padStart(2, '0')}</span>
              <span className="rounded border border-border px-1.5 py-px uppercase tracking-wide">
                {item.level}
              </span>
              <span className="rounded border border-border px-1.5 py-px">{item.format}</span>
              <span className="inline-flex items-center gap-1">
                <Timer className="h-3 w-3" />
                {item.time_limit_s}с
              </span>
            </div>
            <p className="text-sm">{item.stem_md}</p>
          </li>
        ))}
      </ol>

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" />
        Ключи ответов и детальные параметры не передаются — видно только то, что выставляет ItemView.
      </p>
    </article>
  )
}