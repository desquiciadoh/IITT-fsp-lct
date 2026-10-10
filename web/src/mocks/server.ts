import { setupServer } from 'msw/node'
import { qualificationHandlers } from '@/mocks/handlers/qualification'

/** Node-side MSW server for unit tests (vitest). */
export const server = setupServer(...qualificationHandlers)
