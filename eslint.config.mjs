import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    '.next/**',
    'out/**',
    'build/**',
    'next-env.d.ts',
    // 本リポジトリ固有（アプリコード以外は Lint 対象外）
    '.open-next/**',
    'content/**',
    'docs/**',
    // 🔴 `tools/**` は原則 Lint 対象外だが、Gem Index の中核アルゴリズム（`tools/gem-pool/**`）と
    //    その呼び出し元（`tools/generate_gem_digest.mjs`）だけは対象に戻す（`SP-17` / PR #416
    //    セルフレビュー指摘）。`.mjs` は `tsc --noEmit` の対象でもないため、除外したままだと
    //    約 1,000 行の production 算出コードが lint・型のすべてのゲート外に置かれる。
    'tools/!(gem-pool|generate_gem_digest.mjs)/**',
    'tools/*.!(mjs)',
  ]),
])

export default eslintConfig
