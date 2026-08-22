import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// 🔴 ランタイム分離（`test.projects`・Vitest 4 の推奨形）
//    アプリ層（`{app,src}/**`）はブラウザ相当（jsdom + jest-dom）で、ビルド時ツール
//    （`tools/**`）は実行時と同じ Node ランタイムで走らせる。両者を 1 つの environment に
//    混ぜると、Node 22 専用のツールが jsdom 上で実行され、`fetch` / `URL` / `Buffer` の
//    実装差に依存する退行がテストをすり抜ける（`SP-17` / PR #416 セルフレビュー指摘）。
export default defineConfig({
  test: {
    projects: [
      {
        plugins: [react()],
        resolve: { tsconfigPaths: true },
        test: {
          name: 'app',
          environment: 'jsdom',
          setupFiles: ['./vitest.setup.ts'],
          include: ['{app,src}/**/*.{test,spec}.{ts,tsx}'],
          globals: true,
        },
      },
      {
        // ビルド時ツール（Gem 候補プール生成等）。実行は `node tools/...` なので
        // テストも Node ランタイムで走らせ、jsdom 用の setupFiles は読み込まない。
        test: {
          name: 'tools',
          environment: 'node',
          setupFiles: [],
          include: ['tools/**/*.{test,spec}.mjs'],
          globals: true,
        },
      },
    ],
  },
})
