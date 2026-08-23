import { defineConfig, devices } from '@playwright/test'

import { buildDummyGitHubEnv } from '../../../../e2e/stub/e2e-env.mjs'

/**
 * スライド用スクリーンショット撮影の Playwright 設定。
 *
 * 既存の E2E 基盤（スタブ GitHub API + 本番ビルドのアプリ）をそのまま流用し、
 * 外部ネットワークに依存せず決定論的な画面を撮る。撮影対象と用途は
 * `content/slides_plan.json` の `screenshots` を正本とする。
 *
 * 🔴 L-126: クラウドコンテナの Chromium は TLS 1.3 のハンドシェイクが決定論的に失敗するため、
 * `--ssl-version-max=tls1.2` を必ず渡す（ルートの `playwright.config.ts` と同じ理由）。
 */
const repoRoot = process.cwd()
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3100'
const stubPort = process.env.E2E_STUB_PORT ?? '8788'

export default defineConfig({
  testDir: '.',
  testMatch: 'capture.spec.ts',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  timeout: 120_000,
  use: {
    baseURL,
    deviceScaleFactor: 2, // 縮小して合成するため 2 倍で撮る（文字が潰れない）
  },
  // スライドではスマホ表示を主役に、PC 表示を添えとして合成する（飼い主の指示・2026-08-22）。
  // どちらのプロジェクトも同じ capture.spec.ts を走らせ、ファイル名は project 名で分ける。
  projects: [
    {
      name: 'mobile',
      use: {
        ...devices['Pixel 7'],
        viewport: { width: 393, height: 852 },
        deviceScaleFactor: 2,
        launchOptions: { args: ['--ssl-version-max=tls1.2'] },
      },
    },
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
        launchOptions: { args: ['--ssl-version-max=tls1.2'] },
      },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command: 'node e2e/stub/server.mjs',
          // webServer の既定 cwd は設定ファイルのあるディレクトリなので、リポジトリルートへ寄せる。
          cwd: repoRoot,
          env: { E2E_STUB_PORT: stubPort },
          port: Number(stubPort),
          reuseExistingServer: true,
          timeout: 30_000,
        },
        {
          // 🔴 `.open-next/assets` を先に用意する（**撮影のための細工ではなく、既知の不具合の回避**）。
          // `next start` でも `@opennextjs/cloudflare` の platform proxy が `wrangler.jsonc` の
          // `assets.directory`（`.open-next/assets`）を見る ASSETS binding を作るため、OpenNext ビルドを
          // 挟まないと Gem 候補プール（`/data/gem-index/*`）が **HTTP 404** になり、Gem バッジも
          // Gem 一覧も出ない（`main` の E2E が赤い原因と同一。Issue #454 / #455 / #457）。
          // 配信元は `public/` そのものなので、そこへ向けたシンボリックリンクを張れば実データで撮れる。
          // ⚠️ **#454 / #455 / #457 が解決したらこの前段を外す**（既に実体があるときは何もしない）。
          command:
            '[ -e .open-next/assets ] || (mkdir -p .open-next && ln -s ../public .open-next/assets); npm run build && npm start -- --port 3100',
          cwd: repoRoot,
          env: { ...buildDummyGitHubEnv({ stubPort, appUrl: baseURL }), PORT: '3100' },
          url: baseURL,
          reuseExistingServer: true,
          timeout: 300_000,
        },
      ],
})
