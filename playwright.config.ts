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
            // SP-8: ダミー OAuth 設定を注入したローカルビルド（`infrastructure-design.md` §8.1）。
            // 4 変数が揃うことでログイン導線が有効化される（`src/composition/auth.ts`）。
            // stub は値を検証しないため固定文字列でよい（whiteboard `sp8-auth-i18n-20260819` 争点 D）。
            GITHUB_OAUTH_ORIGIN: `http://127.0.0.1:${stubPort}`,
            GITHUB_OAUTH_CLIENT_ID: 'e2e-dummy-client-id',
            GITHUB_OAUTH_CLIENT_SECRET: 'e2e-dummy-client-secret',
            GITHUB_OAUTH_CALLBACK_URL: 'http://127.0.0.1:3100/api/auth/callback',
            // E2E 専用の 32 バイトダミー鍵（base64url）。本番の値とは無関係。
            SESSION_ENCRYPTION_KEY: 'Z2VtLWh1bnRlci1lMmUtZHVtbXktc2Vzc2lvbi0zMmI',
            PORT: '3100',
          },
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
})
