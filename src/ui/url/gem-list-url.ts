import { buildSearchUrl, type SearchUrlState } from './build-search-url'
import { SEARCH_PARAM_KEYS, type RawSearchParams } from './search-params'

/**
 * 検索結果で実際にバッジが付いた `fullName` を、Gem 一覧（`/{locale}/gems`）の URL へ
 * 同伴させるための表現（Issue #453・案3' scoped hybrid）。
 *
 * 検索結果のバッジは「候補プールに載っているか」の所属照会で付くのに対し、Gem 一覧は
 * repo 名・パッケージ名の全語 AND・単語境界一致で絞り込むため、両者は一致しない
 * （`q=next.js` で一覧が 1 件に落ちる不整合）。GitHub API の追加呼び出しをせず、検索結果側で
 * 既に判明している `fullName` を URL でそのまま一覧へ渡すことで解決する。
 *
 * 🔴 **正規化（上限件数・不正形式のスキップ）はここでは行わない**（`src/usecases/search-gems.ts`
 * の責務）。本ファイルは URL のクエリ文字列表現を組み立て/解析するだけの、表示層に閉じた
 * 純粋関数（`domain` / `infrastructure` を import しない）。
 */

/**
 * `badgedFullNames` を `SearchUrlState` の検索条件へ付け足した URL を組み立てる。
 *
 * `buildSearchUrl` の `extraParams` は空文字の値を省略する契約（`build-search-url.ts`）なので、
 * `badgedFullNames` が空配列（`join(',')` が `''` になる）のときは `badged` クエリ自体が付かない。
 * 値の URL エンコードは `buildSearchUrl` 内部の `URLSearchParams` に委ねる（ここではしない）。
 */
export function buildGemListUrl(
  basePath: string,
  state: SearchUrlState,
  badgedFullNames: readonly string[],
): string {
  return buildSearchUrl(basePath, state, {
    [SEARCH_PARAM_KEYS.badged]: badgedFullNames.join(','),
  })
}

/**
 * URL に載っていた `badged` の **生の値**（カンマ分割・正規化はしない）。
 *
 * `rawKeywordOf`（`search-params.ts`）と同じ流儀: 同名クエリが配列で届いたら先頭の値を採り、
 * 未指定は空文字へ倒す。
 */
export function rawBadgedOf(searchParams: RawSearchParams): string {
  const value = searchParams[SEARCH_PARAM_KEYS.badged]
  return (Array.isArray(value) ? value[0] : value) ?? ''
}
