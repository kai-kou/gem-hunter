import type { NextRequest } from 'next/server'

import {
  buildAuthorizeUrl,
  callbackOrigin,
  makeGithubOAuth,
  oauthCredentialsConfigured,
} from '../infrastructure/github/oauth'
import {
  decodeSessionCookie,
  encodeSessionCookie,
  readSessionCookieFromRequestScope,
  sessionEncryptionConfigured,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_TTL_SECONDS,
} from '../infrastructure/platform/session-cookie'
import { makeCompleteLogin, type CompleteLogin } from '../usecases/complete-login'

/**
 * composition root（認証・AR-5）。`app/api/auth/**` はこのファイル経由でのみ実装へアクセスする
 * （ARCH-3）。CSRF `state` の値自体（生成・照合）は route handler が `next/server` の
 * Cookie API で直接扱う（秘匿値を持たないため ARCH-3 対象外・whiteboard 争点 C 決定）。
 * ただし Cookie **名**（`OAUTH_STATE_COOKIE_NAME`）は 3 つの route handler 間で食い違うと
 * サイレントに壊れるため、ここで一元管理する（PR #141 レビュー指摘）。
 */

/** CSRF state を保持する短命 Cookie の名前（`login` が発行し `callback` が照合する）。 */
export const OAUTH_STATE_COOKIE_NAME = 'oauth_state'

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

/**
 * ログイン/ログアウト完了後のリダイレクト先ホストを決める（オープンリダイレクト対策・
 * PR #141 レビュー指摘）。クライアント送信の `Host` ヘッダをそのまま信頼せず、
 * `GITHUB_OAUTH_CALLBACK_URL` から導出した許可ホストと一致する場合のみそれを使い、
 * 一致しない・比較不能な場合は許可ホスト側へフォールバックする。
 * （`next start --hostname` 未指定時に `request.nextUrl.host` が `localhost` へ正規化され
 * 実際に到達したホストと食い違う実機バグの回避と、Host ヘッダ偽装への対処を両立する。）
 */
export function resolveLandingHost(requestHost: string): string {
  const allowed = callbackOrigin()
  if (!allowed) {
    return requestHost
  }
  const allowedHost = new URL(allowed).host
  return requestHost === allowedHost ? requestHost : allowedHost
}

/**
 * Cookie の `Secure` 属性に使う値を、実際の接続プロトコルから決める。
 *
 * 🔴 ローカル E2E（`http://127.0.0.1`）で `secure: true` を固定値にしていたところ、
 * Chromium が「非 TLS 接続で Secure Cookie を受理する」実装（ループバックを潜在的に
 * 信頼できるオリジンとして扱う）を持ちながらも、そのクッキーの永続化が不安定
 * （直後の `fetch()` で消えていることがある・実機で複数回再現）だったため、
 * 実際に HTTPS で受信したリクエストにのみ `Secure` を付ける方式に改める
 * （本番は Cloudflare Workers 経由で常に HTTPS のため、そちらの安全性は変わらない）。
 * PR #141 レビュー指摘（Step 2 の flaky）への対応。
 */
export function isSecureConnection(protocol: string): boolean {
  return protocol === 'https:'
}

/**
 * ログイン/ログアウト完了後に遷移する先。US-2 と同じくロケール未指定は `/` → 既定ロケールへ
 * （`next.config.ts`）。`app/api/auth/callback/route.ts` と `app/api/auth/logout/route.ts` の
 * 両方が使う（一字一句同じ実装が 2 箇所にあるとオープンリダイレクト対策が片方だけ修正される
 * 事故が起きうるため、ここへ集約・PR #141 レビュー指摘の姉妹対応）。
 *
 * 🔴 `request.url`（`request.nextUrl`）はそのまま使わない。`next start`（`--hostname` 未指定）は
 * 内部的に `localhost` を既定ホストとして `NextURL` を組み立てることがあり、クライアントが実際に
 * 到達したホスト（例: `127.0.0.1:3100`）と食い違う場合がある（実機検証済み）。セッション Cookie は
 * 「このレスポンスをどのオリジンで受け取ったか」で暗黙にスコープされる一方、`Location` の
 * ホストが食い違うとブラウザは次のページを **別オリジン** として読み込み、そのオリジンには
 * 送られてこない Cookie を参照できなくなる（レート枠切替が反映されない障害の原因になる）。
 *
 * 🔴 とはいえ受信した `Host` ヘッダをそのまま信頼すると、TLS の SNI で正規ドメインへ接続した上で
 * `Host` ヘッダだけ別ドメインに書き換えるリクエストでオープンリダイレクトが成立してしまう
 * （PR #141 レビュー指摘）。`resolveLandingHost()` で `GITHUB_OAUTH_CALLBACK_URL` から導出した
 * 許可ホストと突き合わせ、一致する場合のみ受信した `Host` を使う。
 */
export function landingUrl(request: NextRequest): URL {
  const requestHost = request.headers.get('host') ?? request.nextUrl.host
  const host = resolveLandingHost(requestHost)
  return new URL('/', `${request.nextUrl.protocol}//${host}`)
}

export { decodeSessionCookie, encodeSessionCookie, SESSION_COOKIE_NAME, SESSION_COOKIE_TTL_SECONDS }

/**
 * Server Component（`app/[locale]/layout.tsx` 等）向けのセッション読み取り。
 * Cookie ストアへの I/O 自体は `session-cookie.ts`（infrastructure 層）に閉じ込め、
 * composition はそれを呼んで復号するだけ（PR #141 レビュー指摘・ARCH-4/5）。
 */
export async function getSessionAccessToken(): Promise<string | null> {
  const raw = await readSessionCookieFromRequestScope()
  if (!raw) {
    return null
  }
  const session = await decodeSessionCookie(raw)
  return session?.accessToken ?? null
}
