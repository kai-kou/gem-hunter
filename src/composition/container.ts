import type { CachePort } from '../domain/ports/cache-port'
import { GithubRepositoryQuery } from '../infrastructure/github/github-repository-query'
import { makeInstallationTokenProvider } from '../infrastructure/github/installation-token'
import { CachingRepositoryQuery } from '../infrastructure/platform/cached-repository-query'
import { InMemoryCache } from '../infrastructure/platform/cache'
import { SystemClock } from '../infrastructure/system-clock'
import { makeGetRepositoryDetail, type GetRepositoryDetail } from '../usecases/get-repository-detail'
import { makeSearchRepositories, type SearchRepositories } from '../usecases/search-repositories'

/**
 * composition root。実装をポートへ束ねてよい唯一の場所（architecture §2.1）。
 * DI コンテナは使わない（YAGNI）。
 */

/**
 * 検索結果のキャッシュ TTL（秒）。60 秒は暫定値（`R-5` のレート枠逆算が未確定のため）。
 * `R-5` が確定したら本値を見直す（現時点では「同じキーワードで数十秒以内に連打しても
 * GitHub API を叩かない」を満たす最小の値として置いている）。
 */
const TTL_SEARCH_SECONDS = 60

/**
 * リポジトリ詳細のキャッシュ TTL（秒）。詳細情報は検索結果より更新頻度が低いと見なし
 * 検索より長め（5 分）に設定した暫定値。根拠・再決定条件は `TTL_SEARCH_SECONDS` と同じ
 * （`R-5` 確定待ち）。
 */
const TTL_DETAIL_SECONDS = 300

/**
 * isolate 内で使い回すキャッシュの単一インスタンス（モジュールスコープ・SP-5）。
 * 関数内で `new` すると呼び出しのたびに空の `Map` になり常に MISS になるため、
 * モジュール読み込み時（isolate 起動時）に 1 回だけ生成する
 * （whiteboard `content/discussions/sp5-cache-design-20260819/whiteboard.md` round3 決定）。
 */
const sharedCache: CachePort = new InMemoryCache(new SystemClock())

function makeCachingRepositoryQuery(onCacheStatus?: (status: 'HIT' | 'MISS') => void) {
  const clock = new SystemClock()
  return new CachingRepositoryQuery({
    inner: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
    cache: sharedCache,
    ttlSeconds: { search: TTL_SEARCH_SECONDS, detail: TTL_DETAIL_SECONDS },
    onCacheStatus,
  })
}

export function searchRepositoriesUseCase(): SearchRepositories {
  return makeSearchRepositories({ repos: makeCachingRepositoryQuery() })
}

/** SP-3: 独立 URL の詳細画面用ユースケースの組み立て（US-16 / US-17 / AC-4）。 */
export function getRepositoryDetailUseCase(): GetRepositoryDetail {
  return makeGetRepositoryDetail({ repos: makeCachingRepositoryQuery() })
}

/**
 * リクエストスコープで HIT/MISS を観測できるファクトリ（SP-5・`X-Cache-Status` ヘッダ付与用）。
 * `status` はこの呼び出し 1 回分のクロージャに閉じる（`sharedCache` はモジュールスコープで共有）。
 */
export function searchRepositoriesWithCacheStatus(): {
  search: SearchRepositories
  getCacheStatus: () => 'HIT' | 'MISS' | undefined
} {
  let status: 'HIT' | 'MISS' | undefined
  const repos = makeCachingRepositoryQuery((s) => {
    status = s
  })
  return {
    search: makeSearchRepositories({ repos }),
    getCacheStatus: () => status,
  }
}
