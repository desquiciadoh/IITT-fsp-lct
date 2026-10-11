import { setupWorker } from 'msw/browser'
import { coreHandlers } from '@/mocks/handlers/core'
import { demoHandlers, demoGapHandlers } from '@/mocks/handlers/demo'
import { gapHandlers } from '@/mocks/handlers/gaps'
import { assessmentHandlers } from '@/mocks/handlers/assessments'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
import { offerHandlers } from '@/mocks/handlers/offers'
import { fspHandlers } from '@/mocks/handlers/fsp'
import { scoutingHandlers } from '@/mocks/handlers/scouting'
import { employerHandlers } from '@/mocks/handlers/employer'
import { labHandlers } from '@/mocks/handlers/lab'

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
          // FE-10 scouting mock BEFORE employerHandlers: its league/pool/
          // shortlist/talent routes must win over the static fixtures in
          // gaps.ts and employer.ts (MSW is first-match-wins).
          ...scoutingHandlers,
          ...employerHandlers,
          ...labHandlers,
          ...coreHandlers,
        ]
      : [
          // Gaps G1–G17 are live on backend (BE.md §2.3). Missing mode only stubs what is still unreleased.
        ]
  const worker = setupWorker(...handlers)
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}
