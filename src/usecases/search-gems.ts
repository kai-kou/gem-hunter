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

/**
 * Gem 一覧の照会結果（`GemPoolSearchResult` + 照合可否）。
 *
 * `unmatchableQuery` は「検索語は空でないのに、照合に使えるトークンが 1 つも取れなかった」状態
 * （日本語だけの検索語など）。**空状態が 2 種類ある** ことを UI が区別できるようにするために持つ:
 *
 * - `unmatchableQuery: false` の 0 件 … 候補プールに載っていない（母集団の限界・`D-36`）
 * - `unmatchableQuery: true` の 0 件 … 照合規則（英数字識別子の単語境界一致・`D-37`）に
 *   かけられなかった（母集団の話ではなく、検索語の側の話）
 *
 * 🔴 **`GemPoolSearchResult`（`GemIndexPort` の契約）は変えない**。「トークン列が空なら
 * 絞り込みなし＝全件」はポートの契約であり、他の呼び出し側の前提でもある。本フラグは
 * 「生の検索語 → トークン列」という変換を持つ本ユースケースだけが判定できる情報なので、
 * ここで積み増す。
 */
export type SearchGemsResult = GemPoolSearchResult & {
  readonly unmatchableQuery: boolean
}

export type SearchGems = (input: SearchGemsInput) => Promise<SearchGemsResult>

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
 * 🔴 **例外: 照合不能な検索語は 0 件へ倒す。** 検索語が空でないのにトークンが 1 つも取れないとき
 * （日本語だけの検索語。`tokenizeQuery` は ASCII 英数字以外を区切りにするため空配列になる）、
 * ポートの契約では「絞り込みなし＝全件」になり、画面が **「『画像処理』の Gem」と名乗って
 * 候補プール全件を出す**（実測 62,483 件）。これは端的に誤った表示なので、ここで 0 件へ倒し
 * `unmatchableQuery: true` を立てる。**ポート側の契約は変えない**（`GemPoolSearchInput#tokens`
 * の「空＝全件」は他の呼び出し側の前提であり、母集団全体を見せたい用途は今後も必要になりうる）。
 * 母数を持たない 0 件なので `page` / `perPage` の解決結果は結果に影響しない。
 *
 * 🔵 `lookupGemIndexes`（`container.ts`）がユースケースを持たないのと非対称に見えるが、
 * こちらは「生の検索語をトークン列へ正規化する」というドメイン規則の適用があるため層を置く
 * （`lookup()` は `fullName` を素通しするだけでドメインの判断が 1 つも無い）。
 *
 * 不正値は例外にせず既定値へ倒す（`tryPageNumber` / `tryParse` の契約・URL 改変で 500 にしない）。
 */
export function makeSearchGems(deps: { gems: GemIndexPort }): SearchGems {
  return async (input) => {
    const tokens = tokenizeQuery(input.query)
    const result = await deps.gems.search({
      tokens,
      page: tryPageNumber(input.page),
      perPage: tryPerPage(input.perPage),
    })

    if (isUnmatchableQuery(input.query, tokens)) {
      /**
       * 🔵 ポートは呼んだうえで結果を捨てる。出典メタデータ（`meta`・`D-29` / `GR-6`）は
       * 候補プールの配信データにしか無く、0 件の画面でも帰属表示は出す必要があるため
       * （`GemIndexPort` は「照合させずにメタだけ返す」口を持たない・YAGNI で足さない）。
       */
      return {
        ...result,
        items: [],
        totalCount: 0,
        usedTokens: [],
        relaxed: false,
        unmatchableQuery: true,
      }
    }
    return { ...result, unmatchableQuery: false }
  }
}

/**
 * 「検索語は入力されているのに、照合に使えるトークンが 1 つも取れなかった」か。
 *
 * 空文字・空白だけの検索語は **対象外**（`false`）。それは「絞り込みなし」であって
 * 「照合できなかった」ではなく、呼び出し側（`app/[locale]/gems/page.tsx`）が
 * `gems.queryRequired` で先に弾いている。
 */
function isUnmatchableQuery(query: string, tokens: readonly string[]): boolean {
  return query.trim().length > 0 && tokens.length === 0
}
