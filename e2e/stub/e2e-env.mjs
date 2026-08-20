// e2e/stub/e2e-env.mjs — E2E / Lighthouse 計測用のダミー GitHub OAuth 環境変数を組み立てる共有ヘルパー。
//
// `playwright.config.ts`（E2E: stub 8788 / app 3100）と `tools/run_lighthouse.mjs`
// （Lighthouse 計測: stub 8799 / app 3101）が同じダミー値セットを個別に複製していたため、
// SP-10 のレビュー指摘（GitGuardian のハードコード Secret 誤検知の再発防止）で 1 箇所に集約した。
// ここに書く値はすべて E2E 専用のダミーで実際の認証情報ではない（stub は値を検証しないため固定文字列でよい・
// `infrastructure-design.md` §8.1 / whiteboard `sp8-auth-i18n-20260819` 争点 D）。
//
// 呼び出し側ごとにスタブのポート番号とアプリの URL が異なる（E2E とパフォーマンス計測のプロセスを
// 衝突させないための意図的な分離）ため、それらは引数で受け取り、この関数自身はポートを固定しない。
//
// プレーンな ESM の .mjs にしているのは、`tools/run_lighthouse.mjs` が素の `node` で実行され
// TypeScript ローダーを持たないため（.ts を直接 import できない）。TypeScript 側
// （`playwright.config.ts`）は `allowJs` + `moduleResolution: "bundler"` により、この .mjs を
// そのまま import できる。

/**
 * @param {{ stubPort: string | number, appUrl: string }} params
 *   stubPort: スタブ GitHub API サーバーのポート番号
 *   appUrl:   起動する Next.js アプリのベース URL（OAuth コールバック URL の組み立てに使う）
 * @returns {Record<string, string>} Next.js の `next start` に渡すダミー環境変数一式
 */
export function buildDummyGitHubEnv({ stubPort, appUrl }) {
  const stubOrigin = `http://127.0.0.1:${stubPort}`
  return {
    GITHUB_API_ORIGIN: stubOrigin,
    GITHUB_OAUTH_ORIGIN: stubOrigin,
    // SP-8: ダミー OAuth 設定を注入したローカルビルド。4 変数が揃うことでログイン導線が有効化される
    // （`src/composition/auth.ts`）。stub は値を検証しないため固定文字列でよい。
    GITHUB_OAUTH_CLIENT_ID: 'e2e-dummy-client-id',
    GITHUB_OAUTH_CLIENT_SECRET: 'e2e-dummy-client-secret',
    GITHUB_OAUTH_CALLBACK_URL: `${appUrl}/api/auth/callback`,
    // E2E 専用の 32 バイトダミー鍵（base64url）。本番の値とは無関係。
    SESSION_ENCRYPTION_KEY: 'Z2VtLWh1bnRlci1lMmUtZHVtbXktc2Vzc2lvbi0zMmI',
  }
}
