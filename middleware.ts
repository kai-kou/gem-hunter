import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { resolveLocalizedPath } from './src/i18n/resolve-locale-path'

/**
 * ロケール未指定パスを既定ロケール（ja）配下へリダイレクトする（US-9 / E-4）。
 * 判定ロジック本体は resolveLocalizedPath（純関数・単体テスト済み）に委譲する。
 *
 * 備考: Next.js 16 で middleware.ts は proxy.ts へ改名され deprecated 扱いになったが、
 * 「機能はそのまま・ファイル名/エクスポート名のみ変更」であり本バージョン(16.3.1)でも
 * 動作するため、担当タスクの指定ファイル名に従い middleware.ts を採用する。
 */
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const target = resolveLocalizedPath(pathname)
  if (target === null) {
    return NextResponse.next()
  }

  const url = request.nextUrl.clone()
  url.pathname = target
  url.search = search
  return NextResponse.redirect(url)
}

export const config = {
  matcher: ['/((?!_next|api|.*\\..*).*)'],
}
