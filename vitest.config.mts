import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['{app,src}/**/*.{test,spec}.{ts,tsx}', 'tools/**/*.{test,spec}.mjs'],
    globals: true,
  },
})
