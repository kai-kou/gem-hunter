import { trySearchKeyword } from '../../domain/model/search-keyword' // arch-ok
import { tryPageNumber } from '../../domain/model/page-number' // arch-ok

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

/**
 * basePath に検索条件を載せた URL パスを組み立てる。
 * page は 1（既定値）のとき、keyword は空のとき出力しない（URL を短く保つ）。
 */
export function buildSearchPath(
  basePath: string,
  params: { keyword: string; page?: number },
): string {
  const search = new URLSearchParams()

  const keyword = params.keyword.trim()
  if (keyword.length > 0) {
    search.set(SEARCH_PARAM_KEYS.keyword, keyword)
  }

  if (params.page != null && params.page > 1) {
    search.set(SEARCH_PARAM_KEYS.page, String(params.page))
  }

  const queryString = search.toString()
  return queryString.length > 0 ? `${basePath}?${queryString}` : basePath
}
