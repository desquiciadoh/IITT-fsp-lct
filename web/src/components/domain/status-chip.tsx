import { cn } from '@/lib/utils'

export type OfferStatus =
  | 'sent'
  | 'viewed'
  | 'accepted'
  | 'declined'
  | 'expired'
  | 'withdrawn'
  | 'interview'
  | 'hired'
  | 'closed'

const STATUS: Record<OfferStatus, { label: string; color: string }> = {
  sent: { label: 'отправлен', color: 'var(--fsp-status-sent)' },
  viewed: { label: 'просмотрен', color: 'var(--fsp-status-viewed)' },
  accepted: { label: 'принят', color: 'var(--fsp-status-accepted)' },
  declined: { label: 'отклонён', color: 'var(--fsp-status-declined)' },
  withdrawn: { label: 'отозван', color: 'var(--fsp-status-withdrawn)' },
  expired: { label: 'истёк', color: 'var(--fsp-status-expired)' },
  interview: { label: 'интервью', color: 'var(--fsp-info)' },
  hired: { label: 'нанят', color: 'var(--fsp-accent)' },
  closed: { label: 'закрыт', color: 'var(--fsp-muted)' },
}

export function StatusChip({
  status,
  className,
}: {
  status: OfferStatus
  className?: string
}) {
  const s = STATUS[status]
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold', className)}
      style={{ color: s.color, backgroundColor: `color-mix(in srgb, ${s.color} 15%, transparent)` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s.color }} />
      {s.label}
    </span>
  )
}
