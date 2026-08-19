import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { resolveLocalizedPath } from './src/shared/i18n/resolve-locale-path'

/**
 * ロケール未指定パスを既定ロケール（ja）配下へリダイレクトする（US-9 / E-4）。
 * 判定ロジック本体は resolveLocalizedPath（純関数・単体テスト済み）に委譲する。
 *
 * 備考: Next.js 16 で middleware.ts は非推奨化され proxy.ts へ改名された
 * （公式ドキュメント node_modules/next/dist/docs/.../file-conventions/middleware.md 参照）。
 * `next build` が非推奨警告を出すため、CP-2 に従い現行の proxy.ts / `proxy` エクスポート名を採用する。
 */
export function proxy(request: NextRequest) {
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
