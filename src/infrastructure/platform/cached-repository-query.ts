import type { RepositoryDetail, SearchResult } from '../../domain/model/repository'
import type { RepositoryFullName } from '../../domain/model/repository-full-name'
import type { SearchQuery } from '../../domain/model/search-query'
import type { CachePort } from '../../domain/ports/cache-port'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { ownerOf, repoOf } from '../../domain/model/repository-full-name'
import {
  type CacheKey,
  readmeCacheKey,
  repositoryCacheKey,
  searchResultCacheKey,
} from './cache-key'

/**
 * `RepositoryQueryPort` をキャッシュ付きで包むデコレータ（SP-5・NFR-5 / NFR-17 / NFR-18）。
 *
 * GitHub 固有の知識は持たない（`RepositoryQueryPort` と `CachePort` にしか依存しない）。
 * HIT/MISS の伝達は `onCacheStatus` コールバックで行い、`CachePort` / `RepositoryQueryPort`
 * のどちらの契約も変更しない（設計は `content/discussions/sp5-cache-design-20260819/whiteboard.md` の
 * lead consensus / verdict を参照）。
 *
 * 404（`findDetail` が `null` を返すケース）はキャッシュしない。
 *
 * 🟡 **single-flight（PR #120 セルフレビュー指摘・修正1）**: `cache.get` → `inner.*` →
 * `cache.set` は非アトミックなため、同一キーへの並行リクエストは両方 MISS になり上流 API を
 * 二重に叩いてしまう。`search` / `findDetail` それぞれにキー単位の in-flight `Promise` マップを
 * 持たせ、後続の呼び出しは新規 fetch を発行せず先行 `Promise` に相乗りする。完了時（成功・失敗
 * いずれも）は該当エントリを必ず削除する（削除を怠るとエラー後に再試行できなくなる）。
 */
export class CachingRepositoryQuery implements RepositoryQueryPort {
  private readonly inFlightSearch = new Map<CacheKey, Promise<SearchResult>>()
  private readonly inFlightDetail = new Map<CacheKey, Promise<RepositoryDetail | null>>()
  private readonly inFlightReadme = new Map<CacheKey, Promise<string | null>>()

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
    return this.readThrough({
      key,
      inFlight: this.inFlightSearch,
      fetch: () => this.deps.inner.search(query),
      ttlSeconds: this.deps.ttlSeconds.search,
      cacheable: () => true,
      reportStatus: () => true,
    })
  }

  async findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null> {
    const key = repositoryCacheKey(ownerOf(name), repoOf(name))
    return this.readThrough({
      key,
      inFlight: this.inFlightDetail,
      fetch: () => this.deps.inner.findDetail(name),
      ttlSeconds: this.deps.ttlSeconds.detail,
      // 404（null）はキャッシュしない（whiteboard 決定事項）。
      cacheable: (result) => result !== null,
      // 404 のときは onCacheStatus を呼ばない（「キャッシュ未使用のフォールスルー」であり
      // HIT/MISS のどちらでもないため）。single-flight に相乗りした側も同じ規約に従う。
      reportStatus: (result) => result !== null,
    })
  }

  /**
   * README を GitHub がレンダリング済みの **未サニタイズ生 HTML** のままキャッシュする
   * （Issue #334 F-4・whiteboard round3 lead 裁定）。サニタイズ済み HTML をキャッシュしない
   * （表示都合の加工をキャッシュ層の ACL に持ち込まない）。
   *
   * TTL は詳細取得（`ttlSeconds.detail`）を流用する。README 専用の TTL は追加しない
   * （whiteboard 裁定: サニタイズ済み HTML の Tier 2 キャッシュ導入は別 Issue で判断する）。
   * 404（README 不在）は `findDetail` と同じくキャッシュしない。
   */
  async findReadme(name: RepositoryFullName): Promise<string | null> {
    const key = readmeCacheKey(ownerOf(name), repoOf(name))
    return this.readThrough({
      key,
      inFlight: this.inFlightReadme,
      fetch: () => this.deps.inner.findReadme(name),
      ttlSeconds: this.deps.ttlSeconds.detail,
      cacheable: (result) => result !== null,
      reportStatus: (result) => result !== null,
    })
  }

  /**
   * read-through（cache.get → 未ヒットなら in-flight 合流 or 新規 fetch → cache.set）の
   * 共通手順。`search` と `findDetail` の重複を括り出したヘルパー（PR #120 セルフレビュー
   * 指摘・修正1 の一部）。
   */
  private async readThrough<T>(opts: {
    key: CacheKey
    inFlight: Map<CacheKey, Promise<T>>
    fetch: () => Promise<T>
    ttlSeconds: number
    cacheable: (result: T) => boolean
    reportStatus: (result: T) => boolean
  }): Promise<T> {
    const cached = await this.deps.cache.get<T>(opts.key)
    if (cached !== null) {
      this.deps.onCacheStatus?.('HIT')
      return cached
    }

    let promise = opts.inFlight.get(opts.key)
    if (!promise) {
      promise = (async () => {
        try {
          const result = await opts.fetch()
          if (opts.cacheable(result)) {
            await this.deps.cache.set(opts.key, result, opts.ttlSeconds)
          }
          return result
        } finally {
          // 成功・失敗いずれでも必ず削除する（削除漏れは「エラー後に再試行できない」
          // というより深刻なバグに直結するため finally で一元管理する）。
          opts.inFlight.delete(opts.key)
        }
      })()
      opts.inFlight.set(opts.key, promise)
    }

    // 相乗り（in-flight に合流した）側は、自分自身はキャッシュから返したわけでは
    // ないため MISS として報告する（先行呼び出しが実際に上流を叩いている最中に
    // 便乗しているだけで、HIT の意味論＝キャッシュ命中とは異なる）。
    const result = await promise
    if (opts.reportStatus(result)) {
      this.deps.onCacheStatus?.('MISS')
    }
    return result
  }
}
