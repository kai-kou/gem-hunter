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
    // 既存インフォグラフィック（1536x864・完全な 16:9）と同じ寸法で撮る。
    viewport: { width: 1536, height: 864 },
    deviceScaleFactor: 1,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1536, height: 864 },
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
          command: 'npm run build && npm start -- --port 3100',
          cwd: repoRoot,
          env: { ...buildDummyGitHubEnv({ stubPort, appUrl: baseURL }), PORT: '3100' },
          url: baseURL,
          reuseExistingServer: true,
          timeout: 300_000,
        },
      ],
})
