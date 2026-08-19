import type { SearchResult } from '../domain/model/repository'
import { searchQuery } from '../domain/model/search-query'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'

export type SearchRepositoriesInput = {
  keyword: string
  page?: number
}

export type SearchRepositories = (input: SearchRepositoriesInput) => Promise<SearchResult>

/** キーワードでリポジトリを検索する（US-6）。 */
export function makeSearchRepositories(deps: { repos: RepositoryQueryPort }): SearchRepositories {
  return async (input) => deps.repos.search(searchQuery(input))
}
