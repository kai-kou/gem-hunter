import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'
import {
  buildGithubAuthorizeUrl,
  isAuthConfigured,
  isSecureConnection,
  OAUTH_STATE_COOKIE_NAME,
} from '@/src/composition/auth'

/**
 * ログイン開始（AR-5）。GitHub authorize へリダイレクトする。
 *
 * CSRF `state` は `crypto.randomUUID()`（生ランダム値・暗号化/署名は不要・YAGNI）を
 * 短命 Cookie に保存する。**値**の生成・検証は composition root を経由せず、このファイルと
 * `callback/route.ts` が `next/server` の Cookie API で直接扱う（秘匿値を扱わないため
 * ARCH-3 対象外・whiteboard `sp8-auth-i18n-20260819` 争点 B/C 決定）。Cookie **名**は
 * 3 route handler 間の食い違いを防ぐため `src/composition/auth.ts` で一元管理する
 * （PR #141 レビュー指摘）。
 */
export { OAUTH_STATE_COOKIE_NAME }
export const OAUTH_STATE_COOKIE_MAX_AGE_SECONDS = 600 // 10分

export async function GET(request: NextRequest) {
  if (!isAuthConfigured()) {
    // 環境変数未設定時は静かに機能を無効化する（`infrastructure-design.md` §8.1）。
    // ログイン導線自体が表示されない前提だが、直接叩かれた場合の防御として 404 にする。
    return NextResponse.json({ error: 'not_configured' }, { status: 404 })
  }

  const state = crypto.randomUUID()
  const response = NextResponse.redirect(buildGithubAuthorizeUrl(state))
  response.cookies.set(OAUTH_STATE_COOKIE_NAME, state, {
    httpOnly: true,
    secure: isSecureConnection(request.nextUrl.protocol),
    sameSite: 'lax',
    path: '/',
    maxAge: OAUTH_STATE_COOKIE_MAX_AGE_SECONDS,
  })
  return response
}
