import { defineConfig, devices } from '@playwright/test'
import { buildDummyGitHubEnv } from './e2e/stub/e2e-env.mjs'
import { resolveChromiumExecutablePath } from './tools/e2e-chromium-executable.mjs'

/**
 * E2E 設定（SP-4・NFR-24 でネットワークを遮断するため、Next.js 本体をスタブ GitHub API へ向けて起動する）。
 *
 * 🔴 L-126: クラウドコンテナの Chromium は TLS 1.3 のハンドシェイクが決定論的に失敗するため、
 * `--ssl-version-max=tls1.2` を必ず渡す（証明書検証の無効化ではない）。
 *
 * `E2E_BASE_URL` が設定されていれば webServer を起動しない（プレビュー URL に対してそのまま実行できるようにする・
 * `sprint-development-rules-detail.md` §2.6）。
 */
// 🔴 #175 Layer1 指摘: config 評価時点で設定することで Playwright ランナー自身（*.spec.ts を実行する
// Node プロセス）の TZ も UTC 固定する。use.timezoneId（ブラウザコンテキスト）/ webServer.env.TZ
// （アプリの子プロセス）だけでは、テストコード側で Date を直接扱うアサーションの TZ が固定されない。
process.env.TZ = 'UTC'

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3100'
const stubPort = process.env.E2E_STUB_PORT ?? '8788'

export default defineConfig({
  testDir: 'e2e',
  testMatch: '**/*.spec.ts',
  // `e2e/workers/**` は Workers ランタイム依存（`wrangler dev`）専用の別スイート
  // （`playwright.workers.config.ts` / `npm run test:e2e:workers`・Issue #188）。
  // 既定の webServer（`next start`）では binding が常に undefined でフェイルオープンし、
  // これらのテストは意図どおり落ちるため既定の実行対象から外す。
  testIgnore: '**/workers/**',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
    // 🔴 #175: テストプロセスの TZ を本番 Workers と同じ UTC に固定する。
    // コンテナ既定 TZ（Asia/Tokyo）のままだと `timeZone: 'Asia/Tokyo'` 明示指定漏れが
    // ローカル/CI では検知できず、UTC で動く本番だけ 9 時間ずれる退行を見逃す。
    timezoneId: 'UTC',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: ['--ssl-version-max=tls1.2'],
          // 🔴 Issue #629: クラウドコンテナのプリインストール Chromium と `@playwright/test`
          // が要求するビルド番号が食い違う環境向けフォールバック（tools/e2e-chromium-executable.mjs
          // が JSDoc で持つ契約どおり、正常系では undefined を返し既定解決に任せる）。
          executablePath: resolveChromiumExecutablePath(),
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
          // 🔴 `node tools/ensure_open_next_assets.mjs` を先に挟む（Issue #454 / #455 / #457）:
          // `next start` は Node.js ランタイムで動くが、`getCloudflareContext({ async: true })`
          // は NEXT_RUNTIME=nodejs でも wrangler の `getPlatformProxy()` を実際に呼び出し、
          // `wrangler.jsonc` の `assets.directory`（`.open-next/assets`）を指す `env.ASSETS` を
          // 用意してしまう。`opennextjs-cloudflare build` を未実行だとこのディレクトリが無く、
          // Gem Index の読み取りが 404 のまま静かに空になり、E2E が「実装は正しいのに落ちる」形で
          // 失敗する。鮮度チェック済みなら再ビルドはスキップされるため、通常時の起動時間はほぼ
          // 変わらない（`tools/ensure_open_next_assets.mjs` 冒頭のコメント参照）。
          // `tools/run_checks.sh` 側にも同じスクリプトを配線済み（ロジックは二重実装しない）。
          command: `node tools/ensure_open_next_assets.mjs && npm run build && npm start -- --port 3100`,
          env: {
            // ダミー GitHub OAuth 環境変数一式は e2e/stub/e2e-env.mjs（共有モジュール）に集約済み。
            // tools/run_lighthouse.mjs（Lighthouse 計測: stub 8799 / app 3101）と同じ値セットを
            // 個別に複製しない（SP-10・GitGuardian 誤検知の再発防止）。
            ...buildDummyGitHubEnv({ stubPort, appUrl: baseURL }),
            PORT: '3100',
            // 🔴 #175: サーバープロセスも UTC 固定（本番 Workers と同条件で JST 表示ロジックを検証する）
            TZ: 'UTC',
          },
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
})
