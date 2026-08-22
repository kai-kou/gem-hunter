import { tokenizeQuery } from '../domain/model/gem-keyword'
import { tryPageNumber } from '../domain/model/page-number'
import { tryParse as tryPerPage } from '../domain/model/per-page'
import type { GemIndexPort, GemPoolSearchResult } from '../domain/ports/gem-index-port'

export type SearchGemsInput = {
  /** 利用者が入力した検索語の **生値**（URL の `q`）。正規化は本ユースケースが行う。 */
  readonly query: string
  /** 1 始まりのページ番号の生値。未指定・不正値は既定ページへ倒す。 */
  readonly page?: string | number | null
  /** 1 ページの表示件数の生値。未指定・不正値は既定表示件数へ倒す。 */
  readonly perPage?: string | number | null
}

export type SearchGems = (input: SearchGemsInput) => Promise<GemPoolSearchResult>

/**
 * 検索語で Gem 候補プールを絞り込み、`gemIndex` 昇順の 1 ページ分を返す（`SP-19` / `D-37`）。
 *
 * URL の生値（`q` / `page` / `per_page`）を **境界でドメインの値へ変換** してから
 * `GemIndexPort` へ委譲するだけの薄い層（`makeSearchRepositories` と同じ形）。
 *
 * 🔴 **照合規則・並べ替え・緩和判定をここへ持ち込まない。** 照合規則の正本は
 * `src/domain/model/gem-keyword.ts`、それを使った絞り込みとページ切り出しは
 * `GemIndexPort#search` の実装（`src/infrastructure/platform/static-gem-index.ts`）の責務。
 * ここで再度並べ替えると、実装側の決定論的な順序（`gemIndex` 昇順・同値は
 * `repositoryFullName` 昇順）と二重管理になる。
 *
 * 🔵 `lookupGemIndexes`（`container.ts`）がユースケースを持たないのと非対称に見えるが、
 * こちらは「生の検索語をトークン列へ正規化する」というドメイン規則の適用があるため層を置く
 * （`lookup()` は `fullName` を素通しするだけでドメインの判断が 1 つも無い）。
 *
 * 不正値は例外にせず既定値へ倒す（`tryPageNumber` / `tryParse` の契約・URL 改変で 500 にしない）。
 */
export function makeSearchGems(deps: { gems: GemIndexPort }): SearchGems {
  return async (input) => {
    return deps.gems.search({
      tokens: tokenizeQuery(input.query),
      page: tryPageNumber(input.page),
      perPage: tryPerPage(input.perPage),
    })
  }
}
