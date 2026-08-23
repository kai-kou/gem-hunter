import { DEFAULT_PAGE, type PageNumber, pageNumber } from './page-number'
import { DEFAULT_PER_PAGE, type PerPage, parse as parsePerPage } from './per-page'
import { type SearchKeyword, searchKeyword } from './search-keyword'
import { DEFAULT_SORT_ORDER, type SortOrder, parse as parseSortOrder } from './sort-order'

/**
 * 検索条件。URL と 1 対 1 で対応する（NFR-2）。
 */
export type SearchQuery = {
  readonly keyword: SearchKeyword
  readonly page: PageNumber
  readonly sort: SortOrder
  readonly perPage: PerPage
}

export function searchQuery(input: {
  keyword: string
  page?: number
  sort?: string
  perPage?: number
}): SearchQuery {
  return {
    keyword: searchKeyword(input.keyword),
    page: input.page === undefined ? (DEFAULT_PAGE as PageNumber) : pageNumber(input.page),
    sort: input.sort === undefined ? DEFAULT_SORT_ORDER : parseSortOrder(input.sort),
    perPage:
      input.perPage === undefined ? (DEFAULT_PER_PAGE as PerPage) : parsePerPage(input.perPage),
  }
}

export function equalsSearchQuery(a: SearchQuery, b: SearchQuery): boolean {
  return (
    a.keyword === b.keyword && a.page === b.page && a.sort === b.sort && a.perPage === b.perPage
  )
}
