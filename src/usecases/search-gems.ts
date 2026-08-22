import { tokenizeQuery } from '../domain/model/gem-keyword'
import { DEFAULT_PAGE } from '../domain/model/page-number'
import { tryParse as tryPerPage } from '../domain/model/per-page'
import type { GemIndexPort, GemPoolSearchResult } from '../domain/ports/gem-index-port'

export type SearchGemsInput = {
  /** 利用者が入力した検索語の **生値**（URL の `q`）。正規化は本ユースケースが行う。 */
  readonly query: string
  /** 1 始まりのページ番号の生値。未指定・不正値は既定ページへ倒す（上限は設けない）。 */
  readonly page?: string | readonly string[] | number | null
  /** 1 ページの表示件数の生値。未指定・不正値は既定表示件数へ倒す。 */
  readonly perPage?: string | number | null
}

/**
 * Gem 一覧の照会結果。**取得できたか（`status`）を最初に区別する**。
 *
 * 🔴 `status: 'failed'` は **候補プールを読めていない**（取得失敗）状態。`GemIndexPort#search` は
 * 失敗しても例外を投げず空の結果を返す契約なので、`totalCount === 0` だけでは「一致が無い」と
 * 区別できず、画面が一時障害を「あなたの検索語には Gem が無い」と誤って伝えてしまう
 * （`ui-ux-guidelines.md` §4.4: 4 状態を別物として設計する）。ここで区別して返す。
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
export type SearchGemsSuccess = GemPoolSearchResult & {
  readonly status: 'ok'
  readonly unmatchableQuery: boolean
}

/** 候補プールを読めていない（取得失敗）。画面は 0 件ではなくエラーと再試行導線を出す。 */
export type SearchGemsFailure = { readonly status: 'failed' }

export type SearchGemsResult = SearchGemsSuccess | SearchGemsFailure

export type SearchGems = (input: SearchGemsInput) => Promise<SearchGemsResult>

/**
 * URL の `page` 生値を Gem 一覧のページ番号（1 始まりの正整数）へ変換する。
 *
 * 🔴 **`tryPageNumber`（`src/domain/model/page-number.ts`）を使わない**。あちらは GitHub 検索 API が
 * 返せる 1,000 件から決まる上限（`MAX_PAGE` = 50）を持つ値オブジェクトで、**Gem 一覧はその上限に
 * 縛られない**。候補プールは 1 語で 8,913 件（`com`）・8,156 件（`github`）・1,631 件（`core`）に
 * 達する実測があり、50 ページで打ち切ると残りが到達不能になる（F-02）。範囲外のページを
 * 最終ページへ丸めるのは、母数を知っている `GemIndexPort#search` の実装の責務
 * （`effectivePage` で実際に返したページが分かる）。
 *
 * 不正値（0・負・小数・非数・巨大値・未指定）は例外にせず既定ページへ倒す（URL 改変で 500 にしない）。
 * 同名クエリが重複して配列で届いたときは先頭の値を採る（`searchParams` の素の形をそのまま受ける）。
 */
export function toGemListPage(
  raw: string | readonly string[] | number | null | undefined,
): number {
  const value = Array.isArray(raw) ? raw[0] : (raw as string | number | null | undefined)
  if (value == null || value === '') {
    return DEFAULT_PAGE
  }
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    return DEFAULT_PAGE
  }
  return parsed
}

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
 * 🔴 **例外 1: 照合不能な検索語は 0 件へ倒す。** 検索語が空でないのにトークンが 1 つも取れないとき
 * （日本語だけの検索語。`tokenizeQuery` は ASCII 英数字以外を区切りにするため空配列になる）、
 * ポートの契約では「絞り込みなし＝全件」になり、画面が **「『画像処理』の Gem」と名乗って
 * 候補プール全件を出す**（実測 62,483 件）。判定は **ポートを呼ぶ前** に行う（F-14）: 後ろに置くと
 * 返さない結果のために検索インデックス構築（実測 tokenize 約 91ms + 並べ替え約 31ms）と
 * 全件走査を丸ごと払う。ただし出典メタデータ（`D-29` / `GR-6`）は 0 件の画面でも要るため、
 * **絞り込みなしで 1 回だけ** 呼ぶ（`GemIndexPort` に「メタだけ返す」口は足さない・YAGNI）。
 *
 * 🔴 **例外 2: 取得失敗を 0 件に潰さない（F-05）。** `GemIndexPort#search` は失敗しても例外を
 * 投げず空の結果を返す契約なので、`totalCount === 0` は「一致が無い」と「プールを読めていない」の
 * どちらでもありうる。**絞り込みなしの母数**（候補プールの件数）が 0 かどうかで両者を分ける
 * （プールが空 = 読めていない）。この確認は 0 件のときだけ行い、ヒットしたときは呼ばない。
 * ⚠️ ポート契約に失敗を表す値（例 `degraded: boolean`）が入れば、この 2 回目の呼び出しは不要になる。
 *
 * 🔵 `lookupGemIndexes`（`container.ts`）がユースケースを持たないのと非対称に見えるが、
 * こちらは「生の検索語をトークン列へ正規化する」というドメイン規則の適用があるため層を置く
 * （`lookup()` は `fullName` を素通しするだけでドメインの判断が 1 つも無い）。
 *
 * 不正値は例外にせず既定値へ倒す（`toGemListPage` / `tryParse` の契約・URL 改変で 500 にしない）。
 */
export function makeSearchGems(deps: { gems: GemIndexPort }): SearchGems {
  return async (input) => {
    const tokens = tokenizeQuery(input.query)
    const perPage = tryPerPage(input.perPage)

    try {
      if (isUnmatchableQuery(input.query, tokens)) {
        // 出典メタデータのためだけの呼び出し。母数を持たない 0 件なので要求ページは持ち込まない。
        const pool = await deps.gems.search({ tokens: [], page: DEFAULT_PAGE, perPage })
        if (pool.totalCount === 0) {
          return { status: 'failed' }
        }
        return {
          ...pool,
          items: [],
          totalCount: 0,
          effectivePage: DEFAULT_PAGE,
          usedTokens: [],
          relaxed: false,
          status: 'ok',
          unmatchableQuery: true,
        }
      }

      const result = await deps.gems.search({
        tokens,
        page: toGemListPage(input.page),
        perPage,
      })
      if (result.totalCount === 0 && (await isPoolUnavailable(deps.gems, perPage))) {
        return { status: 'failed' }
      }
      return { ...result, status: 'ok', unmatchableQuery: false }
    } catch {
      /**
       * 🔵 **二重防御**: ポートは契約上例外を投げないが、投げても一覧ページ全体を 500 に
       * しない（`app/` 配下に `error.tsx` は無い）。取得失敗として扱い、画面は
       * エラーと再試行導線を出す。
       */
      return { status: 'failed' }
    }
  }
}

/**
 * 候補プールそのものを読めていないか（＝絞り込みなしの母数が 0 か）。
 *
 * 実データのプールは 62,483 件あり、健全なら「絞り込みなし」は必ず 1 件以上を返す。
 * 0 件なら読み込みに失敗している（`GemIndexPort#search` の契約では失敗も空結果になる）。
 */
async function isPoolUnavailable(gems: GemIndexPort, perPage: number): Promise<boolean> {
  const pool = await gems.search({ tokens: [], page: DEFAULT_PAGE, perPage })
  return pool.totalCount === 0
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
