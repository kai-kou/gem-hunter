import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { DEFAULT_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_SORT_ORDER } from '@/src/domain/model/sort-order'
import { SEARCH_PARAM_KEYS } from './search-params'

/**
 * 検索条件の現在値（表示・リンク生成用の素朴な形）。
 * `ParsedSearchParams`（`search-params.ts`）と同じ 4 フィールドを持つ。
 */
export type SearchUrlState = {
  keyword: string
  page: number
  sort: string
  perPage: number
}

/**
 * 検索条件を URL クエリへ載せる（SP-7・NFR-2）。
 *
 * 既定値と一致する項目は省略する。`tryParse` 系（`page-number.ts` / `sort-order.ts` /
 * `per-page.ts`）が未指定を既定値へ倒すため、往復しても同じ状態に戻り、URL も簡潔になる。
 *
 * `basePath` を空文字にすると、パスを持たないクエリ文字列（`?q=...` または `''`）だけを返す
 * （一覧カードのリンクへ現在の検索条件を「継ぎ足す」用途・`repository-list.tsx` / `gem-list.tsx`）。
 *
 * `extraParams` は検索 4 条件以外の付帯パラメータ（Gem 一覧の `from=gems` 等）を同じ URL へ
 * 載せるための任意引数。🔴 **URL 契約を組み立てる実装をここ以外に作らない**ための受け口で、
 * 既定値による省略は行わない（渡された値をそのまま載せる）。空文字の値は載せない。
 */
export function buildSearchUrl(
  basePath: string,
  state: SearchUrlState,
  extraParams: Readonly<Record<string, string>> = {},
): string {
  const params = new URLSearchParams()
  if (state.keyword !== '') {
    params.set(SEARCH_PARAM_KEYS.keyword, state.keyword)
  }
  if (state.page !== DEFAULT_PAGE) {
    params.set(SEARCH_PARAM_KEYS.page, String(state.page))
  }
  if (state.sort !== DEFAULT_SORT_ORDER) {
    params.set(SEARCH_PARAM_KEYS.sort, state.sort)
  }
  if (state.perPage !== DEFAULT_PER_PAGE) {
    params.set(SEARCH_PARAM_KEYS.perPage, String(state.perPage))
  }
  for (const [key, value] of Object.entries(extraParams)) {
    if (value !== '') {
      params.set(key, value)
    }
  }
  const qs = params.toString()
  return qs === '' ? basePath : `${basePath}?${qs}`
}
