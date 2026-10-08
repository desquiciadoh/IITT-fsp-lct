import { Navigate } from 'react-router-dom'
import { useMe } from '@/api/me'
import { CardSkeleton } from '@/components/ui/skeleton'

/** `/` → role home. */
export function IndexRedirect() {
  const { data, isLoading } = useMe()
  if (isLoading) {
    return (
      <div className="mx-auto mt-16 max-w-md">
        <CardSkeleton />
      </div>
    )
  }
  if (!data) return <Navigate to="/login" replace />
  if (data.role === 'candidate') return <Navigate to="/candidate" replace />
  if (data.role === 'employer') return <Navigate to="/employer" replace />
  return <Navigate to="/jury" replace />
}
