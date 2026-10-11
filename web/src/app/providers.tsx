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
import { errorMessage } from '@/i18n/errors'

type Meta = Record<string, unknown> | undefined

/**
 * Expired session → clear the cache and send the user to `/login`.
 *
 * `skipAuthRedirect` opts a request out: `useMe` (public pages call it while
 * anonymous) and the auth/persona mutations (they surface their own errors).
 */
function createQueryClient() {
  const ref: { client?: QueryClient } = {}
  let isRedirecting = false

  const handleError = (error: unknown, meta: Meta) => {
    if (!(error instanceof ApiError) || error.status !== 401) return
    if (meta?.skipAuthRedirect) return
    const from = router.state.location.pathname
    if (from === '/login' || isRedirecting) return
    isRedirecting = true
    ref.client?.clear()
    void router
      .navigate(`/login?next=${encodeURIComponent(from)}`, { replace: true })
      .finally(() => {
        isRedirecting = false
      })
    toast.error(errorMessage('unauthorized'), { id: 'session-expired' })
  }

  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: (n, e) =>
          !(e instanceof ApiError && (e.status === 401 || e.status === 403)) && n < 1,
        refetchOnWindowFocus: false,
        staleTime: 15_000,
      },
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
