import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import { buildDummyGitHubEnv } from './e2e/stub/e2e-env.mjs'

/**
 * E2E 設定（SP-4・NFR-24 でネットワークを遮断するため、Next.js 本体をスタブ GitHub API へ向けて起動する）。
 *
 * 🔴 L-126: クラウドコンテナの Chromium は TLS 1.3 のハンドシェイクが決定論的に失敗するため、
 * `--ssl-version-max=tls1.2` を必ず渡す（証明書検証の無効化ではない）。
 *
 * `E2E_BASE_URL` が設定されていれば webServer を起動しない（プレビュー URL に対してそのまま実行できるようにする・
 * `sprint-development-rules-detail.md` §2.6）。
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3100'
const stubPort = process.env.E2E_STUB_PORT ?? '8788'
// SP-16: `sort=gemIndex` を検索スタブ（`many-hits` 60 件データセット）と決定論的に突合させるための
// 固定候補プール（`GemDigestPort` の差し替え口・`e2e/sp-16.spec.ts` 冒頭コメント参照）。
const gemDigestFixturePath = path.join(__dirname, 'e2e/fixtures/gem-digest-pool.json')

export default defineConfig({
  testDir: 'e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: ['--ssl-version-max=tls1.2'],
        },
      },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command: `node e2e/stub/server.mjs`,
          env: { E2E_STUB_PORT: stubPort },
          port: Number(stubPort),
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
        },
        {
          command: `npm run build && npm start -- --port 3100`,
          env: {
            // ダミー GitHub OAuth 環境変数一式は e2e/stub/e2e-env.mjs（共有モジュール）に集約済み。
            // tools/run_lighthouse.mjs（Lighthouse 計測: stub 8799 / app 3101）と同じ値セットを
            // 個別に複製しない（SP-10・GitGuardian 誤検知の再発防止）。
            ...buildDummyGitHubEnv({ stubPort, appUrl: baseURL }),
            GEM_DIGEST_SOURCE_PATH: gemDigestFixturePath,
            PORT: '3100',
          },
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
})
