import { readFileSync } from 'node:fs'

import type { CachePort } from '../domain/ports/cache-port'
import type { ClockPort } from '../domain/ports/clock-port'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import type { TokenProvider } from '../infrastructure/github/github-repository-query'
import { GithubRepositoryQuery } from '../infrastructure/github/github-repository-query'
import { makeInstallationTokenProvider } from '../infrastructure/github/installation-token'
import { CachingRepositoryQuery } from '../infrastructure/platform/cached-repository-query'
import { InMemoryCache } from '../infrastructure/platform/cache'
import { SystemClock } from '../infrastructure/system-clock'
import { StaticGemDigest } from '../infrastructure/platform/static-gem-digest'
import { makeGetDailyDigest, type GetDailyDigest } from '../usecases/get-daily-digest'
import {
  makeGetRepositoryDetail,
  type GetRepositoryDetail,
} from '../usecases/get-repository-detail'
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

/**
 * SP-8: レート枠切替（AR-5）。`accessToken` があればユーザー自身のアクセストークンを、
 * 無ければ従来どおり installation token（GitHub App 共有枠）を使う `TokenProvider` を返す。
 * `RateLimitPort`（Issue #122・自リクエストの間引き）とは無関係な別配線
 * （whiteboard `sp8-auth-i18n-20260819` C-3 決定・両者を同一関数に混在させない）。
 * 新規ドメインポートは追加しない（`TokenProvider` は既に `github-repository-query.ts` 内で
 * 抽象化済みの infra 内部の型）。
 */
function makeTokenProvider(clock: ClockPort, accessToken?: string | null): TokenProvider {
  if (accessToken) {
    return async () => accessToken
  }
  return makeInstallationTokenProvider({ clock })
}

function makeCachingRepositoryQuery(
  deps: {
    onCacheStatus?: (status: 'HIT' | 'MISS') => void
    accessToken?: string | null
  } = {},
) {
  const clock = new SystemClock()
  return new CachingRepositoryQuery({
    inner: new GithubRepositoryQuery({ token: makeTokenProvider(clock, deps.accessToken) }),
    cache: sharedCache,
    ttlSeconds: { search: TTL_SEARCH_SECONDS, detail: TTL_DETAIL_SECONDS },
    onCacheStatus: deps.onCacheStatus,
  })
}

/**
 * Gem Index 候補プールの取得口を組み立てる（`SP-14` の `getDailyDigestUseCase()` と
 * `SP-16` の `searchRepositoriesUseCase()` が同じ差し替え口を共有する・whiteboard
 * `sp16-gem-index-sort-20260821` round3 決定 8）。
 *
 * `GEM_DIGEST_SOURCE_PATH` が設定されていれば、本番の `public/data/daily-digest.json`
 * ではなくそのパスの JSON を候補プールとして読む（E2E 専用の固定候補プールを注入し、
 * 検索スタブの `repositoryFullName` と一致させて決定論的に検証するための差し替え口）。
 * 本番では未設定のため常に既定の静的 JSON を使う。読み込みに失敗した場合も例外にせず
 * 既定の候補プールへフォールバックする（`GemDigestPort` の「例外を投げない」契約・
 * `static-gem-digest.ts` と同じ fail-soft 方針）。
 */
function makeGemDigestPort(): GemDigestPort {
  const overridePath = process.env.GEM_DIGEST_SOURCE_PATH
  if (!overridePath) {
    return new StaticGemDigest()
  }
  try {
    const raw = readFileSync(overridePath, 'utf-8')
    return new StaticGemDigest(JSON.parse(raw))
  } catch (cause) {
    console.warn(
      `[container] GEM_DIGEST_SOURCE_PATH（${overridePath}）の読み込みに失敗しました。既定の候補プールへフォールバックします: ${String(cause)}`,
    )
    return new StaticGemDigest()
  }
}

/**
 * SP-5: 検索結果の取得（HIT/MISS の観測は `searchRepositoriesWithCacheStatus()` を使う）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で検索する（省略時は installation token）。
 * SP-16: `sort=gemIndex` の並べ替え用に `GemDigestPort`（候補プール）を束ねる。
 */
export function searchRepositoriesUseCase(accessToken?: string | null): SearchRepositories {
  return makeSearchRepositories({
    repos: makeCachingRepositoryQuery({ accessToken }),
    gemDigest: makeGemDigestPort(),
  })
}

/**
 * SP-3: 独立 URL の詳細画面用ユースケースの組み立て（US-16 / US-17 / AC-4）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で取得する（省略時は installation token）。
 */
export function getRepositoryDetailUseCase(accessToken?: string | null): GetRepositoryDetail {
  return makeGetRepositoryDetail({ repos: makeCachingRepositoryQuery({ accessToken }) })
}

/**
 * リクエストスコープで HIT/MISS を観測できるファクトリ（SP-5・`X-Cache-Status` ヘッダ付与用）。
 * `status` はこの呼び出し 1 回分のクロージャに閉じる（`sharedCache` はモジュールスコープで共有）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で検索する。
 */
export function searchRepositoriesWithCacheStatus(accessToken?: string | null): {
  search: SearchRepositories
  getCacheStatus: () => 'HIT' | 'MISS' | undefined
} {
  let status: 'HIT' | 'MISS' | undefined
  const repos = makeCachingRepositoryQuery({
    accessToken,
    onCacheStatus: (s) => {
      status = s
    },
  })
  return {
    search: makeSearchRepositories({ repos, gemDigest: makeGemDigestPort() }),
    getCacheStatus: () => status,
  }
}

/**
 * SP-14: キーワード非依存の日次ダイジェスト（`ADR 0014`）。候補プールは静的 JSON
 * （`StaticGemDigest`・`D-28`）から読み、並べ替えは usecase 側で日付シードから決定論的に行う。
 * サーバー側に状態を持たない（`D-6` / `D-14`）ため、リクエストごとに使い捨てで組み立ててよい。
 * SP-16: 候補プールの読み込み元は `searchRepositoriesUseCase()` と共通の `makeGemDigestPort()`
 * を使う（`GEM_DIGEST_SOURCE_PATH` の差し替え口を共有・whiteboard round3 決定 8）。
 */
export function getDailyDigestUseCase(): GetDailyDigest {
  return makeGetDailyDigest({ port: makeGemDigestPort() })
}
