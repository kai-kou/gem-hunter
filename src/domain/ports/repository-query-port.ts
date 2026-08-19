import type { SearchResult } from '../model/repository'
import type { SearchQuery } from '../model/search-query'

/**
 * リポジトリ情報の取得口（NFR-16）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 */
export interface RepositoryQueryPort {
  search(query: SearchQuery): Promise<SearchResult>
}
