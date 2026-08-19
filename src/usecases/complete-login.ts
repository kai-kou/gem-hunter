import type { AuthPort } from '../domain/ports/auth-port'

export type CompleteLoginResult = { accessToken: string }
export type CompleteLogin = (code: string) => Promise<CompleteLoginResult>

/**
 * OAuth コールバックの認可コードをアクセストークンへ交換する（AR-5）。
 * ポートを引数で受け取る（ARCH-2）ため、テストはフェイクの `AuthPort` を渡すだけで済む。
 * state（CSRF）検証は本ユースケースの外（route handler）が担う
 * （state は Cookie 由来の web セキュリティ artifact であり業務規則ではない・
 * whiteboard `sp8-auth-i18n-20260819` C-2 決定）。
 */
export function makeCompleteLogin(deps: { auth: AuthPort }): CompleteLogin {
  return async (code: string) => deps.auth.exchangeAuthorizationCode(code)
}
