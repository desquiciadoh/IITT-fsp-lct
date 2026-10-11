import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from '@/app/router'
import { AppProviders } from '@/app/providers'
import '@/index.css'

// MSW is a dev-only layer (VITE_API_MOCKS=all|missing). It must stay out of
// the production entry chunk, so the whole mock tree is loaded dynamically
// and only when mocks are actually enabled. R30: entry-chunk budget.
async function enableMocksIfNeeded(): Promise<void> {
  const mode = import.meta.env.VITE_API_MOCKS ?? 'off'
  if (mode === 'off') return
  const { startMocks } = await import('@/mocks/browser')
  await startMocks()
}

void enableMocksIfNeeded().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  )
})
