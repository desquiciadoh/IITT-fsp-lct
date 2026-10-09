import type { LucideIcon } from 'lucide-react'
import { Info, ListChecks, Minus, PenLine, Plus, Trophy, Beaker } from 'lucide-react'
import type { Reason, ReasonKind, Source } from '@/api/types'
import { cn } from '@/lib/utils'

const KIND_ICON: Record<ReasonKind, LucideIcon> = {
  plus: Plus,
  minus: Minus,
  info: Info,
}

const KIND_COLOR: Record<ReasonKind, string> = {
  plus: 'var(--fsp-plus)',
  minus: 'var(--fsp-minus)',
  info: 'var(--fsp-info)',
}

/** Evidence source metadata. `verified` drives the shared chip look (R7). */
export const SOURCE_META: Record<
  Source,
  { icon: LucideIcon; short: string; verified: boolean; title: string; chipClass?: string }
> = {
  test: { icon: Beaker, short: 'тест', verified: true, title: 'подтверждено тестом' },
  fsp: { icon: Trophy, short: 'ФСП', verified: true, title: 'подтверждено ФСП' },
  microtask: {
    icon: ListChecks,
    short: 'задача',
    verified: true,
    title: 'подтверждено микрозадачей (FE-16)',
    chipClass: 'border-info/40 text-info',
  },
  declared: { icon: PenLine, short: 'заявлено', verified: false, title: 'заявлено кандидатом' },
}

/** Verified vs declared must look different (UX rule); microtask has its own tone (FE-16). */
export function sourceChipClass(verified: boolean, chipClass?: string) {
  if (chipClass) return chipClass
  return verified
    ? 'border-border text-foreground'
    : 'border-dashed border-muted-foreground/60 text-muted-foreground'
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
      {reasons.map((r, i) => {
        const meta = r.source ? SOURCE_META[r.source] : undefined
        const KindIcon = KIND_ICON[r.kind]
        return (
          <span
            key={i}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
              meta
                ? sourceChipClass(meta.verified, meta.chipClass)
                : 'border-border',
            )}
          >
            <KindIcon className="h-3 w-3" style={{ color: KIND_COLOR[r.kind] }} />
            <span>{r.text}</span>
            {meta && (
              <span
                className="ml-0.5 inline-flex items-center gap-0.5 text-[10px] font-semibold uppercase"
                title={meta.title}
              >
                <meta.icon className="h-3 w-3" />
                {meta.short}
              </span>
            )}
          </span>
        )
      })}
    </div>
  )
}
