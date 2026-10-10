import { setupServer } from 'msw/node'
import { qualificationHandlers } from '@/mocks/handlers/qualification'
import { employerHandlers } from '@/mocks/handlers/employer'

/** Node-side MSW server for unit tests (vitest). */
export const server = setupServer(...qualificationHandlers, ...employerHandlers)
