import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import {
  completeLoginUseCase,
  encodeSessionCookie,
  isAuthConfigured,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_TTL_SECONDS,
} from '@/src/composition/auth'

/**
 * OAuth コールバック（AR-5）。`code`/`state` を受け取り、state を検証してからトークン交換し、
 * セッション Cookie を発行する。
 *
 * 🔴 `OAUTH_STATE_COOKIE_NAME` は `app/api/auth/login/route.ts` と同じ値を持つ（`oauth_state`）。
 * Next.js の route.ts は HTTP メソッド以外の任意 export を持たせない運用にしているため
 * （ビルド時の route export 検証との相性を避ける）、定数は各ファイルへ意図的に複製している
 * （値は whiteboard `sp8-auth-i18n-20260819` 争点 B/C で `oauth_state` に確定済み・実装手段の選択）。
 */
const OAUTH_STATE_COOKIE_NAME = 'oauth_state'

/**
 * ログイン成否に関わらず遷移する先。US-2 と同じくロケール未指定は `/` → 既定ロケールへ（next.config.ts）。
 *
 * 🔴 `request.url`（`request.nextUrl`）はそのまま使わない。`next start`（`--hostname` 未指定）は
 * 内部的に `localhost` を既定ホストとして `NextURL` を組み立てることがあり、クライアントが実際に
 * 到達したホスト（例: `127.0.0.1:3100`）と食い違う場合がある（実機検証済み）。セッション Cookie は
 * 「このレスポンスをどのオリジンで受け取ったか」で暗黙にスコープされる一方、`Location` の
 * ホストが食い違うとブラウザは次のページを **別オリジン** として読み込み、そのオリジンには
 * 送られてこない Cookie を参照できなくなる（レート枠切替が反映されない障害の原因になる）。
 * 受信した `Host` ヘッダをそのまま使い、クライアントが到達したオリジンを保つ。
 */
function landingUrl(request: NextRequest): URL {
  const host = request.headers.get('host') ?? request.nextUrl.host
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
      secure: true,
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
