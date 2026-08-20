import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import { OAUTH_STATE_COOKIE_NAME, resolveLandingHost, SESSION_COOKIE_NAME } from '@/src/composition/auth'

/**
 * ログアウト（AR-5）。セッション Cookie を破棄して元の画面へ戻す。
 * 単純なリンクから叩けるよう GET にする（`login-link.tsx` は `next/link` の `<Link>`。
 * フォーム/JS を要求しない・実装手段の選択・SD-3 対象外。CSRF での強制ログアウトは実害が
 * 小さいと判断し許容する・PR #141 レビュー指摘への回答）。
 *
 * `oauth_state` は callback 成功時点で既に削除済みのはずだが、フロー中断
 * （state 不一致・認可拒否等）で残る可能性があるため防御的に同名 Cookie も削除する
 * （whiteboard `sp8-auth-i18n-20260819` 争点 B 根拠 5）。Cookie 名は
 * `src/composition/auth.ts` で一元管理する（PR #141 レビュー指摘）。
 */

/** `app/api/auth/callback/route.ts` の `landingUrl()` と同じ理由（オープンリダイレクト対策）。 */
function landingUrl(request: NextRequest): URL {
  const requestHost = request.headers.get('host') ?? request.nextUrl.host
  const host = resolveLandingHost(requestHost)
  return new URL('/', `${request.nextUrl.protocol}//${host}`)
}

export async function GET(request: NextRequest) {
  const response = NextResponse.redirect(landingUrl(request))
  response.cookies.delete(SESSION_COOKIE_NAME)
  response.cookies.delete(OAUTH_STATE_COOKIE_NAME)
  return response
}
