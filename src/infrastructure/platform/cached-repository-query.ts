import type { RepositoryDetail, SearchResult } from '../../domain/model/repository'
import type { RepositoryFullName } from '../../domain/model/repository-full-name'
import type { SearchQuery } from '../../domain/model/search-query'
import type { CachePort } from '../../domain/ports/cache-port'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { ownerOf, repoOf } from '../../domain/model/repository-full-name'
import { repositoryCacheKey, searchResultCacheKey } from './cache-key'

/**
 * `RepositoryQueryPort` をキャッシュ付きで包むデコレータ（SP-5・NFR-5 / NFR-17 / NFR-18）。
 *
 * GitHub 固有の知識は持たない（`RepositoryQueryPort` と `CachePort` にしか依存しない）。
 * HIT/MISS の伝達は `onCacheStatus` コールバックで行い、`CachePort` / `RepositoryQueryPort`
 * のどちらの契約も変更しない（設計は `content/discussions/sp5-cache-design-20260819/whiteboard.md` の
 * lead consensus / verdict を参照）。
 *
 * 404（`findDetail` が `null` を返すケース）はキャッシュしない。
 */
export class CachingRepositoryQuery implements RepositoryQueryPort {
  constructor(
    private readonly deps: {
      inner: RepositoryQueryPort
      cache: CachePort
      ttlSeconds: { search: number; detail: number }
      onCacheStatus?: (status: 'HIT' | 'MISS') => void
    },
  ) {}

  async search(query: SearchQuery): Promise<SearchResult> {
    const key = searchResultCacheKey(query)
    const cached = await this.deps.cache.get<SearchResult>(key)
    if (cached !== null) {
      this.deps.onCacheStatus?.('HIT')
      return cached
    }
    const result = await this.deps.inner.search(query)
    await this.deps.cache.set(key, result, this.deps.ttlSeconds.search)
    this.deps.onCacheStatus?.('MISS')
    return result
  }

  async findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null> {
    const key = repositoryCacheKey(ownerOf(name), repoOf(name))
    const cached = await this.deps.cache.get<RepositoryDetail>(key)
    if (cached !== null) {
      this.deps.onCacheStatus?.('HIT')
      return cached
    }
    const result = await this.deps.inner.findDetail(name)
    if (result === null) {
      // 404 はキャッシュしない（whiteboard 決定事項）。onCacheStatus も呼ばない
      // （「キャッシュ未使用のフォールスルー」であり HIT/MISS のどちらでもないため）。
      return null
    }
    await this.deps.cache.set(key, result, this.deps.ttlSeconds.detail)
    this.deps.onCacheStatus?.('MISS')
    return result
  }
}
