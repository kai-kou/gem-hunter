import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import {
  completeLoginUseCase,
  encodeSessionCookie,
  isAuthConfigured,
  isSecureConnection,
  landingUrl,
  OAUTH_STATE_COOKIE_NAME,
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
 * ログイン成否に関わらず遷移する先。`landingUrl()` の実装（オープンリダイレクト対策込み）は
 * `app/api/auth/logout/route.ts` と共通のため `src/composition/auth.ts` に集約している
 * （PR #141 レビュー指摘・重複解消）。
 */

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
