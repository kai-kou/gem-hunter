import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import { OAUTH_STATE_COOKIE_NAME, resolveLandingHost, SESSION_COOKIE_NAME } from '@/src/composition/auth'

/**
 * ログアウト（AR-5）。セッション Cookie を破棄して元の画面へ戻す。
 * **POST 限定**（GET にしない）: `next/link` の `<Link>` は本番ビルドでビューポート内リンクを
 * 自動プリフェッチするため、GET にすると `login-link.tsx` を表示しただけで
 * `GET /api/auth/logout` が実行されセッションが破棄されてしまう（Playwright トレースで実測・
 * 307 応答と `set-cookie` 空文字化を確認）。ブラウザ/プロキシの先読みでも同様に誤爆しうる。
 * `login-link.tsx` 側は `<form method="post" action="/api/auth/logout">` から叩く。
 * CSRF 対策: セッション Cookie は `sameSite: 'lax'`（`src/composition/auth.ts`）のため、
 * クロスサイトからの POST 送信では Cookie が付与されず攻撃は成立しない。専用の CSRF トークン
 * 導入は Issue #144 に残る。
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

export async function POST(request: NextRequest) {
  const response = NextResponse.redirect(landingUrl(request))
  response.cookies.delete(SESSION_COOKIE_NAME)
  response.cookies.delete(OAUTH_STATE_COOKIE_NAME)
  return response
}
