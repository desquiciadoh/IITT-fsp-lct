import { Badge } from '@/components/ui/badge'

const ACCEPTANCE_META: Record<'low' | 'medium' | 'high', { label: string; variant: 'danger' | 'warning' | 'success' }> = {
  low: { label: 'низкая вероятность', variant: 'danger' },
  medium: { label: 'средняя вероятность', variant: 'warning' },
  high: { label: 'высокая вероятность', variant: 'success' },
}

/** FE-17 · ML-10 acceptance likelihood, shown next to "Send". */
export function AcceptanceBadge({
  value,
}: {
  value?: 'low' | 'medium' | 'high' | null
}) {
  if (!value) return null
  const meta = ACCEPTANCE_META[value]
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}