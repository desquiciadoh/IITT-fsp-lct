import { cn } from '@/lib/utils'
import { SOURCE_META, sourceChipClass } from '@/components/domain/reason-chips'
import type { Source } from '@/api/types'

/**
 * Skill chip following the same verified-vs-declared convention as reasons:
 * verified skills are solid, declared ones are dashed and muted.
 */
export function SkillChip({ name, source = 'declared' }: { name: string; source?: Source }) {
  const meta = SOURCE_META[source]
  const Icon = meta.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs',
        sourceChipClass(meta.verified, meta.chipClass),
      )}
    >
      <Icon className="h-3 w-3" />
      {name}
      <span className="text-[10px] font-semibold uppercase opacity-80" title={meta.title}>
        {meta.short}
      </span>
    </span>
  )
}
