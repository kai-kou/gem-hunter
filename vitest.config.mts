import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    // `tools/` はビルド時ツール（アプリ層ではない）。Gem 候補プール生成の純粋関数を
    // ユニットテストするため .mjs も対象に含める（`SP-17` / Issue #387）。
    include: ['{app,src}/**/*.{test,spec}.{ts,tsx}', 'tools/**/*.{test,spec}.mjs'],
    globals: true,
  },
})
