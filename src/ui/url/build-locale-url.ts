import type { Locale } from '../../domain/model/locale'

/**
 * 現在のパス（AR-4 により全ページに言語プレフィックスが付く・`/ja/...` `/en/...`）と
 * 切り替え先の `Locale` から、遷移先 URL を組み立てる純粋関数（US-2・SP-8）。
 * `build-search-url.ts` と同じ置き場所・パターンを踏襲する。
 *
 * 先頭の言語セグメントだけを差し替え、それ以外のパス・クエリ文字列（検索条件等）は
 * そのまま保持する。SP-7 で確立した「操作を跨いでも現在の検索条件（keyword/page/sort/perPage）を
 * 保つ」という方針（`build-search-url.ts` / `pagination.tsx` 等）と同じ考え方を言語切替にも適用する
 * （言語を切り替えただけで検索結果や表示中のページが失われるのは体験として不自然なため）。
 */
export function buildLocaleUrl(currentPath: string, targetLocale: Locale): string {
  const queryIndex = currentPath.indexOf('?')
  const pathname = queryIndex === -1 ? currentPath : currentPath.slice(0, queryIndex)
  const query = queryIndex === -1 ? '' : currentPath.slice(queryIndex)

  const withoutLeadingSlash = pathname.startsWith('/') ? pathname.slice(1) : pathname
  const slashIndex = withoutLeadingSlash.indexOf('/')
  const restOfPath = slashIndex === -1 ? '' : withoutLeadingSlash.slice(slashIndex)

  return `/${targetLocale}${restOfPath}${query}`
}
