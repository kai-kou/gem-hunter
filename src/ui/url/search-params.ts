import { trySearchKeyword } from '@/src/domain/model/search-keyword'
import { tryPageNumber } from '@/src/domain/model/page-number'
import { tryParse as tryPerPage } from '@/src/domain/model/per-page'
import { tryParse as trySortOrder } from '@/src/domain/model/sort-order'

/**
 * 検索条件を URL クエリへ載せるためのパラメータ名契約（US-9 / AC-2 / NFR-2）。
 * 名前・既定値・許容値の正本は docs/02_requirements/prd.md §2.4.1 で、本定数はその実装。
 * 1 箇所に固定し、この名前を他ファイルへ直書きしない。
 */
export const SEARCH_PARAM_KEYS = {
  keyword: 'q',
  page: 'page',
  sort: 'sort',
  perPage: 'per_page',
} as const

export type RawSearchParams = Record<string, string | string[] | undefined>

export type ParsedSearchParams = {
  keyword: string
  page: number
  sort: string
  perPage: number
}

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

/**
 * URL に載っていたキーワードの **生の値**（妥当性判定・既定値への丸めをしない）。
 *
 * `parseSearchParams()` は「不正値は例外を投げず既定値へ倒す」設計のため、キーワードが
 * ドメインの不変条件を満たさないと `''`（＝未入力）に潰れる。未入力とエラーを画面で
 * 区別する側（`app/[locale]/page.tsx`）はこちらを使う。
 */
export function rawKeywordOf(input: RawSearchParams): string {
  return firstValue(input[SEARCH_PARAM_KEYS.keyword]) ?? ''
}

/**
 * URL の生の値を素直な形へ正規化する（ドメインの妥当性判定は
 * `trySearchKeyword` / `tryPageNumber` / `tryParse`（`per-page` / `sort-order`）に委ねる。
 * 不正値は例外を投げず既定値へ倒す）。
 */
export function parseSearchParams(input: RawSearchParams): ParsedSearchParams {
  const rawKeyword = firstValue(input[SEARCH_PARAM_KEYS.keyword])
  const rawPage = firstValue(input[SEARCH_PARAM_KEYS.page])
  const rawSort = firstValue(input[SEARCH_PARAM_KEYS.sort])
  const rawPerPage = firstValue(input[SEARCH_PARAM_KEYS.perPage])

  const keyword = trySearchKeyword(rawKeyword) ?? ''
  const page = tryPageNumber(rawPage)
  const sort = trySortOrder(rawSort)
  const perPage = tryPerPage(rawPerPage)

  return { keyword, page, sort, perPage }
}
