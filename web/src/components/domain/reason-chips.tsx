import type { ReactNode } from 'react'
import { Info, ListChecks, Minus, PenLine, Plus, Trophy, Beaker } from 'lucide-react'
import type { Reason, ReasonKind, Source } from '@/api/types'
import { cn } from '@/lib/utils'

const KIND_ICON: Record<ReasonKind, ReactNode> = {
  plus: <Plus className="h-3 w-3" />,
  minus: <Minus className="h-3 w-3" />,
  info: <Info className="h-3 w-3" />,
}

const KIND_COLOR: Record<ReasonKind, string> = {
  plus: 'var(--fsp-plus)',
  minus: 'var(--fsp-minus)',
  info: 'var(--fsp-info)',
}

const SOURCE_META: Record<Source, { icon: ReactNode; title: string }> = {
  test: { icon: <Beaker className="h-3 w-3" />, title: 'подтверждено тестом' },
  fsp: { icon: <Trophy className="h-3 w-3" />, title: 'подтверждено ФСП' },
  microtask: { icon: <ListChecks className="h-3 w-3" />, title: 'микрозадача' },
  declared: { icon: <PenLine className="h-3 w-3" />, title: 'заявлено кандидатом' },
}

export function ReasonChips({
  reasons,
  className,
}: {
  reasons: Reason[]
  className?: string
}) {
  if (reasons.length === 0) return null
  return (
    <div className={cn('flex flex-wrap gap-1.5', className)}>
      {reasons.map((r, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs"
          style={{ color: KIND_COLOR[r.kind] }}
        >
          {KIND_ICON[r.kind]}
          <span className="text-foreground">{r.text}</span>
          {r.source && (
            <span
              className="ml-0.5 inline-flex items-center gap-0.5 text-muted-foreground"
              title={SOURCE_META[r.source].title}
            >
              {SOURCE_META[r.source].icon}
            </span>
          )}
        </span>
      ))}
    </div>
  )
}
