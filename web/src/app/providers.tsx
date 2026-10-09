import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { Toaster, toast } from 'sonner'
import { useState, type ReactNode } from 'react'
import { router } from '@/app/router'
import { ApiError } from '@/api/client'
import { retryQuery } from '@/api/retry'
import { errorMessage } from '@/i18n/errors'

type Meta = Record<string, unknown> | undefined

/**
 * Expired session → clear the cache and send the user to `/login`.
 *
 * `skipAuthRedirect` opts a request out: `useMe` (public pages call it while
 * anonymous) and the auth/persona mutations (they surface their own errors).
 */
function createQueryClient() {
  const ref: { client?: QueryClient; redirecting?: boolean } = {}

  const handleError = (error: unknown, meta: Meta) => {
    if (!(error instanceof ApiError) || error.status !== 401) return
    if (meta?.skipAuthRedirect) return
    const from = router.state.location.pathname
    // One redirect and one toast for a burst of parallel 401s (R21).
    if (from === '/login' || ref.redirecting) return
    ref.redirecting = true
    ref.client?.clear()
    toast.error(errorMessage('unauthorized'), { id: 'session-expired' })
    void router
      .navigate(`/login?next=${encodeURIComponent(from)}`, { replace: true })
      .finally(() => {
        ref.redirecting = false
      })
  }

  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: retryQuery, refetchOnWindowFocus: false, staleTime: 15_000 },
    },
    queryCache: new QueryCache({
      onError: (error, query) => handleError(error, query.meta),
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) =>
        handleError(error, mutation.meta),
    }),
  })
  ref.client = client
  return client
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(createQueryClient)
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  )
}
