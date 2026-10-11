/// <reference types="vitest/config" />
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // changeOrigin must stay false so Django's CSRF origin check
      // sees http://localhost:5173 as the origin (FE1.md §1).
      '/api': { target: 'http://127.0.0.1:8000' },
      '/admin': { target: 'http://127.0.0.1:8000' },
    },
  },
  build: {
    // R30 · Split the eager vendor libs out of the entry chunk so it stays
    // small. Modules not listed here keep their default chunk (so lazily
    // imported libs — shiki, recharts, react-markdown — stay off the critical
      // path and load only with their route).
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('react-router')) return 'react-router'
          if (id.includes('react-dom') || id.includes('/react/') || id.includes('scheduler'))
            return 'react'
          if (id.includes('@tanstack')) return 'tanstack'
          if (id.includes('radix-ui')) return 'radix'
          if (id.includes('react-hook-form') || id.includes('@hookform')) return 'hookform'
          if (id.includes('/zod/')) return 'zod'
          if (id.includes('lucide-react')) return 'lucide'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
