import { defineConfig, devices } from '@playwright/test'
import { buildDummyGitHubEnv } from './e2e/stub/e2e-env.mjs'

/**
 * Workers ランタイム依存の振る舞い（レート制限・binding）を検証する E2E 専用設定（Issue #188）。
 *
 * `playwright.config.ts`（既定）は `next start`（Node.js ランタイム）でアプリを起動するため、
 * `rateLimiterBinding()`（`src/infrastructure/platform/cloudflare-bindings.ts`）は常に `undefined` を
 * 返しフェイルオープンで即 return する（Workers ランタイムの外）。この設定は `wrangler dev`
 * （workerd・ローカル実行）を webServer に使うことで、`RATE_LIMITER` binding を実際に経由させる。
 *
 * 🔴 既定の `npm run test:e2e` からは分離する（実行時間・ポートの衝突を避けるため）。
 * `npm run test:e2e:workers` で単独実行できる。`tools/run_checks.sh` にも配線済み
 * （実測 約50秒・E2E/Lighthouse と同程度のため既定ゲートに組み込んだ・Issue #669）。
 */
process.env.TZ = 'UTC'

const appPort = process.env.E2E_WORKERS_APP_PORT ?? '8798'
const stubPort = process.env.E2E_WORKERS_STUB_PORT ?? '8789'
const baseURL = `http://127.0.0.1:${appPort}`

// wrangler dev の `--var KEY:VALUE` は 1 フラグにつき 1 変数（playwright.config.ts の
// webServer.env のような形では渡せないため、コマンド文字列側へ展開する）。
const varFlags = Object.entries(buildDummyGitHubEnv({ stubPort, appUrl: baseURL }))
  .concat([['RATE_LIMIT_SALT', 'workers-e2e-dummy-salt']])
  .map(([key, value]) => `--var ${key}:${value}`)
  .join(' ')

export default defineConfig({
  testDir: 'e2e/workers',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
    timezoneId: 'UTC',
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
  webServer: [
    {
      command: `node e2e/stub/server.mjs`,
      env: { E2E_STUB_PORT: stubPort },
      port: Number(stubPort),
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      // ビルド鮮度チェック（既定の e2e と同じツールを再利用・ロジックは二重実装しない） →
      // `wrangler dev` で workerd 上に起動する（`env.RATE_LIMITER` / `env.ASSETS` を実配線）。
      command: `node tools/ensure_open_next_assets.mjs && npx wrangler dev --port ${appPort} ${varFlags}`,
      port: Number(appPort),
      reuseExistingServer: !process.env.CI,
      // opennextjs-cloudflare build（未キャッシュ時）+ wrangler dev 起動を待つ。
      timeout: 180_000,
    },
  ],
})
