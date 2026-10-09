import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useMe } from '@/api/me'
import type { Me } from '@/api/types'
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

/**
 * Where the onboarding gate must send this user, or null to pass through.
 * While `qualification` the backend keeps the step until the test is finished,
 * so the runner and the result page must stay reachable.
 */
export function onboardingRedirect(
  me: Pick<Me, 'role' | 'onboarding_step'> | null | undefined,
  pathname: string,
): string | null {
  if (!me || me.role !== 'candidate') return null
  const step = me.onboarding_step
  if (step === 'consent' || step === 'profile') return `/candidate/onboarding/${step}`
  if (step === 'qualification' && !pathname.startsWith('/candidate/qualification/')) {
    return '/candidate/qualification/start'
  }
  return null
}

/** Candidates must walk through onboarding before entering the app. */
export function OnboardingGate() {
  const { data, isLoading } = useMe()
  const location = useLocation()
  if (isLoading) return <CenteredSpinner />
  if (!data) return <Navigate to="/login" replace />
  const to = onboardingRedirect(data, location.pathname)
  if (to) return <Navigate to={to} replace />
  return <Outlet />
}
