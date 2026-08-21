import type { SearchResult } from '../domain/model/repository'
import { searchQuery } from '../domain/model/search-query'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'

export type SearchRepositoriesInput = {
  keyword: string
  page?: number
  sort?: string
  perPage?: number
}

export type SearchRepositories = (input: SearchRepositoriesInput) => Promise<SearchResult>

/**
 * キーワードでリポジトリを検索する（US-6）。
 * 入力を値オブジェクト（`SearchQuery`）へ変換し、`RepositoryQueryPort` へそのまま委譲する薄い層。
 */
export function makeSearchRepositories(deps: {
  repos: RepositoryQueryPort
}): SearchRepositories {
  return async (input) => {
    const query = searchQuery(input)
    return deps.repos.search(query)
  }
}
