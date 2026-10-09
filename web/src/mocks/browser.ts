import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers, demoGapHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'
import { assessmentHandlers } from '@/mocks/handlers/assessments'
import { offerHandlers } from '@/mocks/handlers/offers'
import { fspHandlers } from '@/mocks/handlers/fsp'

/**
 * VITE_API_MOCKS=all    → mock everything (no backend needed)
 * VITE_API_MOCKS=missing→ mock only real gaps (G1–G17 + demo/reset),
 *                         pass everything the backend serves through
 * VITE_API_MOCKS=off    → no mocks (default)
 */
const mode = import.meta.env.VITE_API_MOCKS ?? 'off'

export async function startMocks(): Promise<void> {
  if (mode === 'off') return
  const handlers =
    mode === 'all'
      ? [
          ...gapHandlers,
          ...demoGapHandlers,
          ...demoHandlers,
          ...assessmentHandlers,
          ...offerHandlers,
          ...fspHandlers,
          ...coreHandlers,
        ]
      : [...gapHandlers, ...demoGapHandlers]
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
