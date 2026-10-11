import { setupServer } from 'msw/node'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
import { offerHandlers } from '@/mocks/handlers/offers'
import { scoutingHandlers } from '@/mocks/handlers/scouting'
import { employerHandlers } from '@/mocks/handlers/employer'

/** Node-side MSW server for unit tests (vitest). */
export const server = setupServer(
  ...qualificationHandlers,
  // FE-11 offers BEFORE scouting/employer — same order as browser.ts.
  ...offerHandlers,
  // BEFORE employerHandlers — same order as browser.ts (first-match-wins).
  ...scoutingHandlers,
  ...employerHandlers,
)
