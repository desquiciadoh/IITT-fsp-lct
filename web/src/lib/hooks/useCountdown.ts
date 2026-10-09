import { useEffect, useState } from 'react'

/**
 * Counts down to an ISO deadline; ticks every second while > 0.
 * Clock-skew aware callers should pass a deadline adjusted on the client
 * (see the runner: measure against `served_at` + local receive time).
 */
export function useCountdown(deadline?: string | null): {
  remainingMs: number
  expired: boolean
} {
  const target = deadline ? new Date(deadline).getTime() : null
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (target === null) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [target])

  if (target === null) return { remainingMs: 0, expired: false }
  const remainingMs = Math.max(0, target - now)
  return { remainingMs, expired: remainingMs === 0 }
}
