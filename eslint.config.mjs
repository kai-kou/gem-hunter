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
    // `wrangler dev`（Issue #188 の Workers ランタイム E2E・`npm run test:e2e:workers`）が
    // ローカルに残す一時バンドル。`.gitignore` 済みだが ESLint の flat config は `.gitignore` を
    // 自動で見ないため、明示的に無視しないと `npx wrangler dev` 実行後の `npm run lint` が
    // このディレクトリの生成物（warning 3 件超）で FAIL する。
    '.wrangler/**',
    'content/**',
    'docs/**',
    // 🔴 `tools/**` は原則 Lint 対象外だが、Gem Index の中核アルゴリズム（`tools/gem-pool/**`）と
    //    その呼び出し元（`tools/generate_gem_digest.mjs`）だけは対象に戻す（`SP-17` / PR #416
    //    セルフレビュー指摘）。`.mjs` は `tsc --noEmit` の対象でもないため、除外したままだと
    //    約 1,000 行の production 算出コードが lint・型のすべてのゲート外に置かれる。
    //    ⚠️ ESLint 9 の flat config では「ディレクトリごと無視（`tools/**`）」した中身は
    //    `!` で戻せない（走査自体が打ち切られる）。直下の子だけを無視（`tools/*`）してから
    //    戻したい対象を `!` で個別に解除する、という公式の書き方に従う。
    'tools/*',
    '!tools/gem-pool',
    '!tools/generate_gem_digest.mjs',
    '!tools/generate_gem_digest.test.mjs',
  ]),
])

export default eslintConfig
