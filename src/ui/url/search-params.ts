import { trySearchKeyword } from '@/src/domain/model/search-keyword'
import { tryPageNumber } from '@/src/domain/model/page-number'

/**
 * 検索条件を URL クエリへ載せるためのパラメータ名契約（US-9 / AC-2）。
 * 1 箇所に固定し、この名前を他ファイルへ直書きしない。
 */
export const SEARCH_PARAM_KEYS = {
  keyword: 'q',
  page: 'page',
} as const

export type RawSearchParams = Record<string, string | string[] | undefined>

export type ParsedSearchParams = {
  keyword: string
  page: number
}

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

/**
 * URL の生の値を素直な形へ正規化する（ドメインの妥当性判定は
 * `trySearchKeyword` / `tryPageNumber` に委ねる。不正値は例外を投げず既定値へ倒す）。
 */
export function parseSearchParams(input: RawSearchParams): ParsedSearchParams {
  const rawKeyword = firstValue(input[SEARCH_PARAM_KEYS.keyword])
  const rawPage = firstValue(input[SEARCH_PARAM_KEYS.page])

  const keyword = trySearchKeyword(rawKeyword) ?? ''
  const page = tryPageNumber(rawPage)

  return { keyword, page }
}
