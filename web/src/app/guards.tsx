import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useMe } from '@/api/me'
import { CardSkeleton } from '@/components/ui/skeleton'

function CenteredSpinner() {
  return (
    <div className="mx-auto mt-16 max-w-md">
      <CardSkeleton />
    </div>
  )
}

export function RequireAuth() {
  const { data, isLoading, isError } = useMe()
  if (isLoading) return <CenteredSpinner />
  if (isError || !data) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RequireRole({ role }: { role: 'candidate' | 'employer' }) {
  const { data } = useMe()
  if (!data) return <Navigate to="/login" replace />
  if (data.role !== role) return <Navigate to="/" replace />
  return <Outlet />
}

/** Candidates must walk through onboarding before entering the app. */
export function OnboardingGate() {
  const { data, isLoading } = useMe()
  const location = useLocation()
  if (isLoading) return <CenteredSpinner />
  if (!data) return <Navigate to="/login" replace />
  const step = data.onboarding_step
  if (data.role === 'candidate' && (step === 'consent' || step === 'profile')) {
    return <Navigate to={`/candidate/onboarding/${step}`} replace />
  }
  if (
    data.role === 'candidate' &&
    step === 'qualification' &&
    location.pathname !== '/candidate/qualification/start'
  ) {
    return <Navigate to="/candidate/qualification/start" replace />
  }
  return <Outlet />
}
