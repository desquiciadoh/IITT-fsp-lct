import { setupServer } from 'msw/node'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
import { scoutingHandlers } from '@/mocks/handlers/scouting'
import { employerHandlers } from '@/mocks/handlers/employer'

/** Node-side MSW server for unit tests (vitest). */
export const server = setupServer(
  ...qualificationHandlers,
  // BEFORE employerHandlers — same order as browser.ts (first-match-wins).
  ...scoutingHandlers,
  ...employerHandlers,
)
