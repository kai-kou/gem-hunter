/**
 * OAuth 認可コードをアクセストークンへ交換する取得口（AR-5・NFR-9）。
 *
 * 実装は `src/infrastructure/github/oauth.ts`（ARCH-5）。ドメイン純度を保つため、
 * ポート名・メソッド名に `Github` / `Cookie` などの実装詳細を持ち込まない
 * （`RepositoryQueryPort` と同じ命名規律）。プロフィール取得（`/user`）は
 * SP-8 のスコープ外（AC 未記載・YAGNI・whiteboard `sp8-auth-i18n-20260819` round2 決定）。
 */
export interface AuthPort {
  /**
   * 認可コードをアクセストークンへ交換する。
   *
   * @param code GitHub から返された OAuth 認可コード（**空でない文字列**）。呼び出し元
   *   `app/api/auth/callback/route.ts` が `!code` で空文字列・欠落を弾いてから渡す
   *   （本ポート自身は空文字列を弾かず、そのままトークンエンドポイントへ送る）。
   * @returns 交換に成功したアクセストークン。
   *
   * 🔴 **異常時の振る舞い**: 例外を投げる（`UpstreamError`）。以下のいずれでも throw する。
   *   - OAuth 資格情報（client id / secret / callback URL）が環境変数に未設定
   *   - トークンエンドポイントへネットワーク到達不能
   *   - 応答が非 2xx（HTTP エラー）
   *   - 応答本文に `error` が含まれる、または `access_token` が欠落
   *   黙って空文字列やフォールバック値を返すことはしない（実装:
   *   `src/infrastructure/github/oauth.ts` の `makeGithubOAuth().exchangeAuthorizationCode`）。
   */
  exchangeAuthorizationCode(code: string): Promise<{ accessToken: string }>
}
