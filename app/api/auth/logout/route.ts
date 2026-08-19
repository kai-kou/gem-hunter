import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import { SESSION_COOKIE_NAME } from '@/src/composition/auth'

/**
 * ログアウト（AR-5）。セッション Cookie を破棄して元の画面へ戻す。
 * 単純なリンクから叩けるよう GET にする（`login-link.tsx` は `next/link` の `<Link>`。
 * フォーム/JS を要求しない・実装手段の選択・SD-3 対象外）。
 *
 * `oauth_state` は callback 成功時点で既に削除済みのはずだが、フロー中断
 * （state 不一致・認可拒否等）で残る可能性があるため防御的に同名 Cookie も削除する
 * （whiteboard `sp8-auth-i18n-20260819` 争点 B 根拠 5）。
 */
const OAUTH_STATE_COOKIE_NAME = 'oauth_state'

/** `app/api/auth/callback/route.ts` の `landingUrl()` と同じ理由で `Host` ヘッダを使う。 */
function landingUrl(request: NextRequest): URL {
  const host = request.headers.get('host') ?? request.nextUrl.host
  return new URL('/', `${request.nextUrl.protocol}//${host}`)
}

export async function GET(request: NextRequest) {
  const response = NextResponse.redirect(landingUrl(request))
  response.cookies.delete(SESSION_COOKIE_NAME)
  response.cookies.delete(OAUTH_STATE_COOKIE_NAME)
  return response
}
