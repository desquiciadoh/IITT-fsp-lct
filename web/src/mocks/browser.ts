import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers, demoGapHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'
import { employerHandlers, employerGapHandlers } from '@/mocks/handlers/employer'
import { assessmentHandlers } from '@/mocks/handlers/assessments'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
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
          // FE-09 stateful company/positions/parse mock FIRST: its wildcard
          // `/api/positions/:id` must win over the static gap stubs (MSW is
          // first-match-wins).
          ...employerHandlers,
          ...gapHandlers,
          ...demoGapHandlers,
          ...demoHandlers,
          // Stateful runner mock FIRST: its eligibility/session endpoints must
          // win over the static fixtures (MSW is first-match-wins, and the
          // wildcard `*/api/assessments/:id` below would otherwise swallow
          // `/api/assessments/eligibility`). Result fixtures for demo ids are
          // still served by assessmentHandlers via `/result`, which cannot
          // collide with any qualification route.
          ...qualificationHandlers,
          ...assessmentHandlers,
          ...offerHandlers,
          ...fspHandlers,
          ...coreHandlers,
        ]
      : [...gapHandlers, ...employerGapHandlers, ...demoGapHandlers]
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
