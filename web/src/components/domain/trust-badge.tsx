import { BadgeCheck, Circle, Globe } from 'lucide-react'
import { cn } from '@/lib/utils'

export type TrustLevel = 'none' | 'domain' | 'verified'

const TRUST: Record<
  TrustLevel,
  { label: string; icon: typeof Circle; className: string; title: string }
> = {
  none: {
    label: 'нет подтверждения',
    icon: Circle,
    className: 'border-border text-muted-foreground',
    title: 'Компания не подтверждена',
  },
  domain: {
    label: 'домен',
    icon: Globe,
    className: 'border-info/40 text-info',
    title: 'Домен компании подтверждён',
  },
  verified: {
    label: 'подтверждена',
    icon: BadgeCheck,
    className: 'border-plus/40 text-plus',
    title: 'Компания подтверждена модерацией',
  },
}

/** Employer/company trust chip (one of the five trust chips). */
export function TrustBadge({
  level,
  showLabel = false,
  className,
}: {
  level: TrustLevel
  showLabel?: boolean
  className?: string
}) {
  const { label, icon: Icon, className: tone, title } = TRUST[level]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
        tone,
        className,
      )}
      title={title}
    >
      <Icon className="h-3 w-3" />
      {showLabel && label}
    </span>
  )
}
