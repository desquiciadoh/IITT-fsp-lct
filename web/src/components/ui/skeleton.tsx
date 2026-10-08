import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader } from '@/components/ui/card'

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  )
}

/** Profile card loading state. */
export function ProfileSkeleton() {
  return (
    <div className="flex items-center gap-4" aria-busy="true" aria-label="Загрузка профиля">
      <Skeleton className="size-12 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  )
}

/** Generic list rows loading state. */
export function RowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Загрузка списка">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-9 w-9 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  )
}

/** Block/card loading state (route-level). */
export function CardSkeleton() {
  return (
    <Card aria-busy="true" aria-label="Загрузка">
      <CardHeader>
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-3 w-1/2" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-4 w-2/3" />
      </CardContent>
    </Card>
  )
}
