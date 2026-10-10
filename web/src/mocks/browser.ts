import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers, demoGapHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'
import { assessmentHandlers } from '@/mocks/handlers/assessments'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
import { offerHandlers } from '@/mocks/handlers/offers'
import { fspHandlers } from '@/mocks/handlers/fsp'
import { scoutingHandlers } from '@/mocks/handlers/scouting'

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
          // FE-10 scouting store FIRST: its `/api/positions/:id` wildcard must
          // win over the static G7 leagues stub below, and the pool/shortlist
          // routes need the stateful set (MSW is first-match-wins).
          ...scoutingHandlers,
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
      : [...gapHandlers, ...demoGapHandlers, ...scoutingHandlers]
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
