const LOOPBACK_HOSTNAMES = new Set(['127.0.0.1', 'localhost', '[::1]'])

/**
 * 環境変数でオリジンを上書きできる箇所の共通ガード（`github-repository-query.ts` の `apiOrigin()` と
 * `oauth.ts` の `oauthOrigin()` が個別に持っていたロジックを統合・PR #141 レビュー指摘）。
 *
 * 🔴 リクエスト時に毎回読む（モジュール読み込み時に固定しない・E-11 / SP-4）。
 * 上書き先はループバックに限定する。認証情報（installation token・OAuth client secret）を
 * 送信するオリジンをこの env 変数ひとつで任意ホストへ切り替えられてしまう
 * （誤設定・混入がそのまま認証情報の流出経路になる）のを防ぐ。
 */
export function resolveLoopbackOverridableOrigin(envVarName: string, defaultOrigin: string): string {
  const configured = process.env[envVarName]
  if (configured === undefined) {
    return defaultOrigin
  }

  let url: URL
  try {
    url = new URL(configured)
  } catch (cause) {
    throw new Error(`${envVarName} の形式が不正です: ${configured}`, { cause })
  }
  if (!LOOPBACK_HOSTNAMES.has(url.hostname)) {
    throw new Error(
      `${envVarName} はループバック（127.0.0.1 / localhost / ::1）のみ許可されています: ${configured}`,
    )
  }
  return configured
}
