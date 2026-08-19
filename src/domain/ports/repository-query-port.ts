import type { RepositoryDetail, SearchResult } from '../model/repository'
import type { RepositoryFullName } from '../model/repository-full-name'
import type { SearchQuery } from '../model/search-query'

/**
 * リポジトリ情報の取得口（NFR-16）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 */
export interface RepositoryQueryPort {
  /** 検索条件に合致するリポジトリの一覧を取得する。 */
  search(query: SearchQuery): Promise<SearchResult>
  /** 単一リポジトリを owner/repo で取得する。存在しない場合は例外にせず null を返す（404 → null）。 */
  findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null>
}
