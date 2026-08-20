/**
 * OAuth 認可コードをアクセストークンへ交換する取得口（AR-5・NFR-9）。
 *
 * 実装は `src/infrastructure/github/oauth.ts`（ARCH-5）。ドメイン純度を保つため、
 * ポート名・メソッド名に `Github` / `Cookie` などの実装詳細を持ち込まない
 * （`RepositoryQueryPort` と同じ命名規律）。プロフィール取得（`/user`）は
 * SP-8 のスコープ外（AC 未記載・YAGNI・whiteboard `sp8-auth-i18n-20260819` round2 決定）。
 */
export interface AuthPort {
  /** 認可コードをアクセストークンへ交換する。失敗時は例外を投げる。 */
  exchangeAuthorizationCode(code: string): Promise<{ accessToken: string }>
}
