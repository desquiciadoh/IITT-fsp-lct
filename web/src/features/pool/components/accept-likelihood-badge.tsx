import type { AcceptLikelihood } from '@/api/types'
import { cn } from '@/lib/utils'

const META: Record<AcceptLikelihood, { label: string; className: string }> = {
  high: { label: 'согласится с высокой вероятностью', className: 'border-plus/40 bg-plus/10 text-plus' },
  medium: { label: 'вероятность средняя', className: 'border-warn/40 bg-warn/10 text-warn' },
  low: { label: 'низкая вероятность согласия', className: 'border-muted-foreground/40 bg-muted text-muted-foreground' },
}

/** FE-17: acceptance-likelihood badge next to "Send". */
export function AcceptLikelihoodBadge({ level }: { level: AcceptLikelihood }) {
  const meta = META[level]
  return (
    <span
      title={meta.label}
      className={cn('shrink-0 rounded-md border px-2 py-0.5 text-xs', meta.className)}
    >
      {level === 'high' ? 'высокая готовность' : level === 'medium' ? 'вероятно согласие' : 'вряд ли примет'}
    </span>
  )
}