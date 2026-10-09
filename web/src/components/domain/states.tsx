import type { ReactNode } from 'react'
import { Inbox, TriangleAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center', className)}>
      <Inbox className="h-8 w-8 text-muted-foreground" />
      <div className="font-semibold">{title}</div>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}

export function ErrorState({
  title = 'Что-то пошло не так',
  description,
  code,
  onRetry,
  className,
}: {
  title?: string
  description?: string
  code?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-8 text-center', className)}>
      <TriangleAlert className="h-8 w-8 text-destructive" />
      <div className="font-semibold">{title}</div>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {code && <code className="text-xs text-muted-foreground">{code}</code>}
      {onRetry && (
        <Button variant="outline" onClick={onRetry} className="mt-1">
          Повторить
        </Button>
      )}
    </div>
  )
}
