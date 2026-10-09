import { cn } from '@/lib/utils'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip, type OfferStatus } from '@/components/domain/status-chip'
import { ReasonChips } from '@/components/domain/reason-chips'
import { TrustBadge, type TrustLevel } from '@/components/domain/trust-badge'
import type { Reason } from '@/api/types'

export type OfferCardOffer = {
  title: string
  company?: { name: string; trust_level?: TrustLevel } | null
  salary_min: number
  salary_max: number
  salary_type: 'gross' | 'net'
  status: OfferStatus
  why_you?: Reason[]
}

export type OfferCardProps = {
  offer: OfferCardOffer
  viewer: 'candidate' | 'employer' | 'jury'
  className?: string
}

export function OfferCard({ offer, viewer, className }: OfferCardProps) {
  const trust = offer.company?.trust_level ?? 'none'
  return (
    <article
      className={cn(
        'flex flex-col gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:bg-secondary',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs uppercase text-muted-foreground">
          {viewer === 'candidate' ? 'Черновик оффера' : viewer === 'employer' ? 'Оффер' : 'Просмотр'}
        </span>
        <StatusChip status={offer.status} />
      </div>
      <div className="font-bold">{offer.title}</div>
      <SalaryTag min={offer.salary_min} max={offer.salary_max} type={offer.salary_type} emphasize />
      {offer.company && (
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {offer.company.name}
          <TrustBadge level={trust} />
        </div>
      )}
      {viewer === 'candidate' && offer.why_you && offer.why_you.length > 0 && (
        <ReasonChips reasons={offer.why_you} />
      )}
    </article>
  )
}
