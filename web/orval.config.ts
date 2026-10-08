import { defineConfig } from 'orval'

export default defineConfig({
  fsp: {
    input: { target: './openapi/schema.json' },
    output: {
      target: './src/api/generated',
      schemas: './src/api/generated/models',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: { path: './src/api/client.ts', name: 'customFetch' },
      },
    },
  },
})
