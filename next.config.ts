import type { NextConfig } from 'next'
import { DEFAULT_LOCALE, LOCALES } from './src/domain/model/locale'
import {
  buildLocaleRedirectDestination,
  buildLocaleRedirectSource,
} from './src/ui/url/locale-redirect'

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
 * リダイレクト要否の判定基準（ロケール接頭辞の有無・静的ファイル拡張子の除外）は
 * `src/shared/i18n/locale-redirect.ts` の `buildLocaleRedirectSource()`（純粋関数）に
 * 一本化されている。他ファイルに同等の判定ロジックは存在しない。
 */
const nextConfig: NextConfig = {
  // `next dev` は AI コーディングエージェントを検知すると `AGENTS.md` / `CLAUDE.md` へ
  // 管理ブロックを自動 upsert する（Next.js 16.3〜）。本リポジトリの `CLAUDE.md` は精緻に
  // 設計済みのプロジェクト正本であり、上書きされると規律全体が壊れるため最初のコミットから
  // 抑止する（Issue #50 T-3。一次情報:
  // node_modules/next/dist/docs/01-app/02-guides/ai-agents.md "Opting out" 節）。
  // 抑止設定そのものの残存は tools/check_claude_md_integrity.py が機械検査する。
  agentRules: false,
  async redirects() {
    return [
      {
        source: '/',
        destination: `/${DEFAULT_LOCALE}`,
        permanent: false,
      },
      {
        // ロケール接頭辞（/ja, /en, ...）・_next・api・末尾セグメントが
        // 静的ファイル拡張子のパスを除く全パスを既定ロケール配下へ前置する。
        // destination を素の `:path` にしない理由は
        // `buildLocaleRedirectDestination()` のコメントを参照（PR #96・OpenNext
        // Cloudflare プレビューでの 500 障害の修正）。
        source: buildLocaleRedirectSource(LOCALES),
        destination: buildLocaleRedirectDestination(DEFAULT_LOCALE),
        permanent: false,
      },
    ]
  },
}

export default nextConfig
