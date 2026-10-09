import { cn } from '@/lib/utils'

export type SalaryType = 'gross' | 'net'

const TYPE_LABEL: Record<SalaryType, string> = {
  gross: 'до вычета',
  net: 'на руки',
}

export function formatSalary(value: number): string {
  return value.toLocaleString('ru-RU').replace(/\u00A0/g, ' ')
}

export function SalaryTag({
  min,
  max,
  type = 'gross',
  currency = '₽',
  className,
  emphasize = false,
}: {
  min: number
  max: number
  type?: SalaryType
  currency?: string
  className?: string
  emphasize?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex items-baseline gap-1 tabular-nums',
        emphasize ? 'text-lg font-bold' : 'text-sm font-semibold',
        className,
      )}
    >
      {formatSalary(min)} – {formatSalary(max)} {currency}
      <span className="text-xs font-medium text-muted-foreground">{TYPE_LABEL[type]}</span>
    </span>
  )
}
