import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'
import { assessmentHandlers } from '@/mocks/handlers/assessments'
import { offerHandlers } from '@/mocks/handlers/offers'
import { fspHandlers } from '@/mocks/handlers/fsp'
import { vacancyHandlers } from '@/mocks/handlers/vacancies'
import { microtaskHandlers } from '@/mocks/handlers/microtasks'
import { poolHandlers } from '@/mocks/handlers/pool'

/**
 * VITE_API_MOCKS=all    → mock everything (no backend needed)
 * VITE_API_MOCKS=missing→ mock only what the backend still lacks (today: nothing);
 *                         everything it serves passes through untagged
 * VITE_API_MOCKS=off    → no mocks (default)
 */
const mode = import.meta.env.VITE_API_MOCKS ?? 'off'

/** G1–G7 and G11 are live on the backend, so nothing is mocked in `missing` mode (R24). */
const missingHandlers: Parameters<typeof setupWorker> = []

export async function startMocks(): Promise<void> {
  if (mode === 'off') return
  const handlers =
    mode === 'all'
      ? [
          ...gapHandlers,
          ...demoHandlers,
          ...assessmentHandlers,
          ...offerHandlers,
          ...fspHandlers,
          ...vacancyHandlers,
          ...microtaskHandlers,
          ...poolHandlers,
          ...coreHandlers,
        ]
      : missingHandlers
  if (handlers.length === 0) return
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
