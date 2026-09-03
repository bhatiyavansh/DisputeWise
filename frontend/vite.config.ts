import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

const BACKEND_URL = process.env.VITE_API_BASE_URL || 'http://localhost:8001'

/**
 * The DisputeWise backend does not send CORS headers (and per this
 * project's explicit rules, the frontend must not modify the backend to add
 * them). Instead of pointing the browser directly at :8001 -- which the
 * browser would then block -- both the dev and preview servers proxy
 * `/cases` and `/health` through to the real backend, so requests are
 * same-origin from the browser's point of view. See docs/frontend.md.
 */
const proxy = {
  '/cases': { target: BACKEND_URL, changeOrigin: true },
  '/health': { target: BACKEND_URL, changeOrigin: true },
  '/simulate': { target: BACKEND_URL, changeOrigin: true },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy,
  },
  preview: {
    port: 4173,
    proxy,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/tests/setup.ts'],
  },
})
