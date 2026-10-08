import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'

/**
 * VITE_API_MOCKS=all    → mock everything (no backend needed)
 * VITE_API_MOCKS=missing→ mock only G1–G17 gap endpoints, pass the rest through
 * VITE_API_MOCKS=off    → no mocks (default)
 */
const mode = import.meta.env.VITE_API_MOCKS ?? 'off'

export async function startMocks(): Promise<void> {
  if (mode === 'off') return
  const handlers =
    mode === 'all'
      ? [...gapHandlers, ...demoHandlers, ...coreHandlers]
      : [...gapHandlers, ...demoHandlers]
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
