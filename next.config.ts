import type { NextConfig } from 'next'
import { DEFAULT_LOCALE, LOCALES } from './src/shared/i18n/config'

/**
 * ロケール未指定パスを既定ロケール（ja）配下へリダイレクトする（US-9 / E-4）。
 *
 * 備考: Next.js 16 で `proxy.ts`（旧 middleware.ts）は既定で Node.js ランタイム固定になり、
 * `runtime` config を proxy 側で上書きすることも不可（設定するとビルドエラーになる）ため、
 * OpenNext Cloudflare アダプタ（Edge 実行）と両立できない
 * （node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md
 *   "Runtime" 節・"Version history" v16.0.0 の記載）。
 * 本リダイレクトは「単純なパス→パスのリダイレクト」であり、公式ドキュメントも
 * 「For simple redirects, consider using the `redirects` configuration in `next.config.ts` first.」
 * と明記しているため、proxy.ts を廃し `redirects()` へ置き換える。
 * リダイレクト要否の判定基準（ロケール接頭辞の有無）は、下記の正規表現
 * （`:path(...)` の否定先読み群）に一本化されている。他ファイルに同等の判定ロジックは存在しない。
 */
const localeAlternation = LOCALES.join('|')

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: '/',
        destination: `/${DEFAULT_LOCALE}`,
        permanent: false,
      },
      {
        // ロケール接頭辞（/ja, /en, ...）・_next・api・拡張子付き静的ファイルを除く
        // 全パスを既定ロケール配下へ前置する。
        source: `/:path((?!(?:${localeAlternation})(?:/|$))(?!_next(?:/|$))(?!api(?:/|$))(?!.*\\..*).*)`,
        destination: `/${DEFAULT_LOCALE}/:path`,
        permanent: false,
      },
    ]
  },
}

export default nextConfig
