import { defineConfig, devices } from '@playwright/test'

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
            GITHUB_API_ORIGIN: `http://127.0.0.1:${stubPort}`,
            PORT: '3100',
          },
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
})
