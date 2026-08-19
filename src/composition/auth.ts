import {
  buildAuthorizeUrl,
  makeGithubOAuth,
  oauthCredentialsConfigured,
} from '../infrastructure/github/oauth'
import {
  decodeSessionCookie,
  encodeSessionCookie,
  sessionEncryptionConfigured,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_TTL_SECONDS,
} from '../infrastructure/platform/session-cookie'
import { makeCompleteLogin, type CompleteLogin } from '../usecases/complete-login'

/**
 * composition root（認証・AR-5）。`app/api/auth/**` はこのファイル経由でのみ実装へアクセスする
 * （ARCH-3）。CSRF `state` Cookie はここを経由しない（route handler が `next/server` の
 * Cookie API で直接生成/照合する・秘匿値を扱わないため ARCH-3 対象外・whiteboard 争点 C 決定）。
 */

/**
 * ログイン導線を表示してよいか。OAuth 3 変数 + セッション暗号鍵の計 4 変数が揃っているかで
 * composition root が一元判定する（`infrastructure-design.md` §8.1: 環境変数未設定で
 * ログイン導線が静かに消える。`app/` にも `src/ui/` にも環境名判定コードを書かない）。
 */
export function isAuthConfigured(): boolean {
  return oauthCredentialsConfigured() && sessionEncryptionConfigured()
}

/** GitHub authorize へのリダイレクト先 URL（`src/infrastructure/github/oauth.ts` の薄いラップ）。 */
export function buildGithubAuthorizeUrl(state: string): string {
  return buildAuthorizeUrl(state)
}

/** OAuth コールバックのユースケース（`AuthPort` 実装として `GithubOAuth` を束ねる）。 */
export function completeLoginUseCase(): CompleteLogin {
  return makeCompleteLogin({ auth: makeGithubOAuth() })
}

export { decodeSessionCookie, encodeSessionCookie, SESSION_COOKIE_NAME, SESSION_COOKIE_TTL_SECONDS }
