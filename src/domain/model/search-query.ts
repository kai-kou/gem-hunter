import { DEFAULT_PAGE, type PageNumber, pageNumber } from './page-number'
import { type SearchKeyword, searchKeyword } from './search-keyword'

/**
 * 検索条件。URL と 1 対 1 で対応する（NFR-2）。
 * ⚠️ ソート順（AR-2）と表示件数（AR-3）は SP-6 / SP-7 で足す。
 */
export type SearchQuery = {
  readonly keyword: SearchKeyword
  readonly page: PageNumber
}

export function searchQuery(input: { keyword: string; page?: number }): SearchQuery {
  return {
    keyword: searchKeyword(input.keyword),
    page: input.page === undefined ? (DEFAULT_PAGE as PageNumber) : pageNumber(input.page),
  }
}

export function equalsSearchQuery(a: SearchQuery, b: SearchQuery): boolean {
  return a.keyword === b.keyword && a.page === b.page
}
