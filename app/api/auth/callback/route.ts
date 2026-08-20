import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import {
  completeLoginUseCase,
  encodeSessionCookie,
  isAuthConfigured,
  isSecureConnection,
  OAUTH_STATE_COOKIE_NAME,
  resolveLandingHost,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_TTL_SECONDS,
} from '@/src/composition/auth'

/**
 * OAuth コールバック（AR-5）。`code`/`state` を受け取り、state を検証してからトークン交換し、
 * セッション Cookie を発行する。
 *
 * `OAUTH_STATE_COOKIE_NAME` は `src/composition/auth.ts` で一元管理する（3 route handler 間で
 * 値が食い違うとログインがサイレントに壊れるため・PR #141 レビュー指摘）。
 */

/**
 * ログイン成否に関わらず遷移する先。US-2 と同じくロケール未指定は `/` → 既定ロケールへ（next.config.ts）。
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
function landingUrl(request: NextRequest): URL {
  const requestHost = request.headers.get('host') ?? request.nextUrl.host
  const host = resolveLandingHost(requestHost)
  return new URL('/', `${request.nextUrl.protocol}//${host}`)
}

/**
 * タイミングセーフな文字列比較（`crypto.timingSafeEqual` は Node 専用で Workers 実行を想定した
 * このファイルでは使わない・`state` は秘匿情報ではないため簡易実装で十分・YAGNI）。
 */
function timingSafeEqualString(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false
  }
  let mismatch = 0
  for (let i = 0; i < a.length; i += 1) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return mismatch === 0
}

export async function GET(request: NextRequest) {
  const failure = NextResponse.redirect(landingUrl(request))
  failure.cookies.delete(OAUTH_STATE_COOKIE_NAME)

  if (!isAuthConfigured()) {
    return failure
  }

  const code = request.nextUrl.searchParams.get('code')
  const stateParam = request.nextUrl.searchParams.get('state')
  const cookieState = request.cookies.get(OAUTH_STATE_COOKIE_NAME)?.value

  if (!code || !stateParam || !cookieState || !timingSafeEqualString(stateParam, cookieState)) {
    return failure
  }

  try {
    const { accessToken } = await completeLoginUseCase()(code)
    const sessionValue = await encodeSessionCookie({ accessToken })

    const success = NextResponse.redirect(landingUrl(request))
    success.cookies.delete(OAUTH_STATE_COOKIE_NAME)
    success.cookies.set(SESSION_COOKIE_NAME, sessionValue, {
      httpOnly: true,
      secure: isSecureConnection(request.nextUrl.protocol),
      sameSite: 'lax',
      path: '/',
      maxAge: SESSION_COOKIE_TTL_SECONDS,
    })
    return success
  } catch {
    // トークン交換失敗（上流エラー・想定外応答）は未ログイン扱いへ倒す。
    return failure
  }
}
