import { defineConfig } from 'orval'

export default defineConfig({
  fsp: {
    input: { target: './openapi/schema.json' },
    output: {
      target: './src/api/generated',
      schemas: './src/api/generated/models',
      // Models only. The app calls the API through the hand-written hooks in
      // `src/api/*.ts`; react-query hooks here would be dead code (R5).
      client: 'fetch',
      clean: true,
    },
  },
})
