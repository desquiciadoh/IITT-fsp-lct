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
  build: {
    // R30: keep the never-imported generated client and static bits out of the
    // entry; split the React ecosystem so the shell chunk stays tiny.
    rollupOptions: {
      output: {
        manualChunks(id) {
          // R30: React-ecosystem vendors get their own cacheable chunk so the
          // app-shell chunk stays tiny (path matching works under pnpm nesting).
          if (
            id.includes('node_modules/react/') ||
            id.includes('node_modules/react-dom/') ||
            id.includes('node_modules/scheduler/') ||
            id.includes('node_modules/react-router') ||
            id.includes('node_modules/@tanstack/react-query/') ||
            id.includes('node_modules/sonner/')
          ) {
            return 'react-vendor'
          }
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // changeOrigin must stay false so Django's CSRF origin check
      // sees http://localhost:5173 as the origin (FE1.md §1).
      '/api': { target: 'http://127.0.0.1:8000' },
      '/admin': { target: 'http://127.0.0.1:8000' },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
