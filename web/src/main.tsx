import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from '@/app/router'
import { AppProviders } from '@/app/providers'
import { CardSkeleton } from '@/components/ui/skeleton'
import '@/index.css'

/** Loads the MSW stack on demand so the mocking library stays out of the main chunk. */
function startMocks() {
  return import('@/mocks/browser').then((m) => m.startMocks())
}

/** Route-level fallback while a lazy chunk loads (R30). */
function RouteFallback() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 py-8">
      <CardSkeleton />
      <CardSkeleton />
    </div>
  )
}

void startMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders>
        <Suspense fallback={<RouteFallback />}>
          <RouterProvider router={router} />
        </Suspense>
      </AppProviders>
    </StrictMode>,
  )
})
