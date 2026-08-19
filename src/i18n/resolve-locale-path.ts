import { DEFAULT_LOCALE, LOCALES } from './config'

/**
 * パスにロケールセグメントが既にあるかを判定する。
 */
function hasLocaleSegment(pathname: string): boolean {
  return LOCALES.some((locale) => pathname === `/${locale}` || pathname.startsWith(`/${locale}/`))
}

/**
 * ロケール未指定のパスを既定ロケール配下へマッピングする純関数。
 * 既にロケールを含む場合は null（リダイレクト不要）を返す。
 */
export function resolveLocalizedPath(pathname: string): string | null {
  if (hasLocaleSegment(pathname)) {
    return null
  }
  const suffix = pathname === '/' ? '' : pathname
  return `/${DEFAULT_LOCALE}${suffix}`
}
