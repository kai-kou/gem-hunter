import type { CachePort } from '../domain/ports/cache-port'
import type { ClockPort } from '../domain/ports/clock-port'
import type { GemIndex } from '../domain/model/gem-index'
import type { TokenProvider } from '../infrastructure/github/github-repository-query'
import { GithubRepositoryQuery } from '../infrastructure/github/github-repository-query'
import { makeInstallationTokenProvider } from '../infrastructure/github/installation-token'
import { CachingRepositoryQuery } from '../infrastructure/platform/cached-repository-query'
import { InMemoryCache } from '../infrastructure/platform/cache'
import { LayeredCache } from '../infrastructure/platform/layered-cache'
import { WorkersCache, workersCacheStorage } from '../infrastructure/platform/workers-cache'
import { SystemClock } from '../infrastructure/system-clock'
import { StaticGemDigest } from '../infrastructure/platform/static-gem-digest'
import { StaticGemIndex } from '../infrastructure/platform/static-gem-index'
import { makeGetDailyDigest, type GetDailyDigest } from '../usecases/get-daily-digest'
import {
  makeGetRepositoryDetail,
  type GetRepositoryDetail,
} from '../usecases/get-repository-detail'
import {
  makeGetRepositoryReadme,
  type GetRepositoryReadme,
} from '../usecases/get-repository-readme'
import { makeSearchGems, type SearchGems } from '../usecases/search-gems'
import { makeSearchRepositories, type SearchRepositories } from '../usecases/search-repositories'

/**
 * composition root。実装をポートへ束ねてよい唯一の場所（architecture §2.1）。
 * DI コンテナは使わない（YAGNI）。
 */

/**
 * 検索結果のキャッシュ TTL（秒）。`R-5`（レート枠の逆算）を 2026-08-20 に実施した結果、
 * 60 秒のままで必要枠を満たすことを確認し、**確定値** とした（暫定値からの変更なし）。
 * 逆算の前提・計算は `docs/05_release/repository-publication-review.md` §7.2、決定の記録は
 * `docs/adr/0005-cache-port-yagni-exception-and-ttl.md` §3.4 の追補が正本。
 * 想定利用規模（`D-3`）が変わったら再逆算する。
 *
 * 🔴 **export しているのは `LayeredCache` の充填 TTL（`refillTtlSeconds`）の上限根拠だから**
 * （`layered-cache.ts` の `DEFAULT_REFILL_TTL_SECONDS` JSDoc）。両者が乖離していないことを
 * `container.test.ts` が機械で固定する（アプリコードからは本ファイル内でしか使わない）。
 */
export const TTL_SEARCH_SECONDS = 60

/**
 * リポジトリ詳細のキャッシュ TTL（秒）。詳細情報は検索結果より更新頻度が低いと見なし
 * 検索より長い 5 分とした。`R-5` の逆算では検索 API（30 req/分）が先に枯れるため詳細側は
 * 律速にならず、300 秒のままで必要枠を満たすことを確認済み（**確定値**）。
 * 根拠の所在・再逆算の条件は `TTL_SEARCH_SECONDS` と同じ。
 */
const TTL_DETAIL_SECONDS = 300

/**
 * トップページの日次ダイジェスト表示件数（`ADR 0014` §2.1 の既定 5 件）。
 *
 * 🔴 元は `src/composition/digest-feed.ts`（RSS 配信専用の composition）に置かれていたが、
 * RSS 撤去（Issue #334 F-5・`D-34`）に伴い消費者がトップページ 1 箇所だけになったため、
 * 製品判断値として `TTL_*_SECONDS` と同じ composition root（本ファイル）へ移設した。
 */
export const DAILY_DIGEST_LIMIT = 5

/**
 * isolate 内で使い回すキャッシュの単一インスタンス（モジュールスコープ・SP-5）。
 * 関数内で `new` すると呼び出しのたびに空の `Map` になり常に MISS になるため、
 * モジュール読み込み時（isolate 起動時）に 1 回だけ生成する
 * （whiteboard `content/discussions/sp5-cache-design-20260819/whiteboard.md` round3 決定）。
 *
 * ⚠️ Workers は複数 isolate へリクエストを分散するため、これ **だけ** では isolate をまたいで
 * 共有されない（プレビュー実測で HIT 率 ≒17%・Issue #121）。実行環境が Cache API を
 * 提供するときは本インスタンスを **1 段目** として残したまま `WorkersCache` を 2 段目に重ね
 * （`LayeredCache`）、Cache API が無い環境（Vitest / Node / ビルド時）では単独で使う。
 */
const inMemoryCache: CachePort = new InMemoryCache(new SystemClock())

/**
 * 実際に使うキャッシュ実装（初回利用時に一度だけ解決する）。
 *
 * 🔴 **モジュール評価時ではなく実行時に判定する**: `caches` は Workers 実行環境のグローバルで、
 * モジュール評価のタイミングによっては未注入でありうる。初回の `get` / `set` まで判定を遅らせる。
 *
 * 🔴 **メモ化するのは成功したときだけ（負のメモ化を作らない）**: フォールバック結果まで
 * 恒久メモ化すると、判定を実行時へ遅らせた狙い（`caches` が後から注入される可能性）が潰れ、
 * その isolate は生存する限り 2 段目を失う。フォールバック時は毎回やり直し、
 * `console.warn` だけを 1 回に抑える（毎リクエストのログ氾濫を避ける）。
 *
 * 🔴 **Cache API で `InMemoryCache` を「置き換え」ない（2 段構成）**: Cloudflare 公式ドキュメント
 * には合成 URL をキーにできるかの記載が無く、プレビュー（ダッシュボードエディタ / Playground）
 * では Cache API 操作が無効と明記されている。置き換えると Cache API が実質 no-op だった場合に
 * HIT 率が現状より悪化しうるため、2 段（isolate 内 → isolate 跨ぎ）にして
 * 最悪でも現状維持に留める（根拠の詳細は `LayeredCache` の JSDoc）。
 */
let resolvedCache: CachePort | undefined

/** フォールバックの警告を isolate ごと 1 回に抑える（再判定のたびには出さない）。 */
let warnedCacheFallback = false

function resolveCache(): CachePort {
  if (resolvedCache) {
    return resolvedCache
  }
  const storage = workersCacheStorage()
  if (storage) {
    // 🔴 **成功したときだけメモ化する**（下の JSDoc の「負のメモ化」を作らない）。
    resolvedCache = new LayeredCache(inMemoryCache, new WorkersCache(storage), {
      // 🔴 充填 TTL を composition root から明示注入する（`layered-cache.ts` の
      //    `DEFAULT_REFILL_TTL_SECONDS` は「合わせる先」を JSDoc で宣言しているだけで、
      //    別ファイルの独立定数なので黙って乖離しうる）。
      refillTtlSeconds: TTL_SEARCH_SECONDS,
    })
    return resolvedCache
  }
  // フォールバックを黙って隠さない（`[AssetReader]` / `[rate-limit]` と同じ流儀の console.warn）。
  // 本番 Workers でこれが出ていたら Cache API の判定が壊れている（isolate 跨ぎの共有が失われる）。
  if (!warnedCacheFallback) {
    warnedCacheFallback = true
    console.warn(
      '[cache] Cache API が使えないため isolate 内メモリキャッシュへフォールバックします',
    )
  }
  // 🔴 **メモ化しない**（次の呼び出しでもう一度判定する）。
  return inMemoryCache
}

/**
 * 上記の解決を挟むだけの委譲。`CachingRepositoryQuery` から見える面は `CachePort` のまま
 * （既存の配線・API シグネチャを変えない）。
 */
const sharedCache: CachePort = {
  get: (key) => resolveCache().get(key),
  set: (key, value, ttlSeconds) => resolveCache().set(key, value, ttlSeconds),
  invalidate: (key) => resolveCache().invalidate(key),
}

/**
 * 日次ダイジェスト（`getDailyDigestUseCase`）が読む候補プールの単一インスタンス
 * （モジュールスコープ）。`StaticGemDigest` は読み取り専用・状態を持たない実装
 * （`static-gem-digest.ts`）なので `sharedCache` のような可変状態の共有ではなく、
 * バンドル済み JSON の再パースを毎リクエスト避けるための使い回しに過ぎない。
 */
const sharedGemDigestPort = new StaticGemDigest()

/**
 * 検索結果カードの Gem バッジ（`SP-18`）が引く候補プール全量の単一インスタンス
 * （モジュールスコープ）。`sharedGemDigestPort` と同じ理由で使い回す: `StaticGemIndex` は
 * 読み取り専用・状態を持たない実装（`static-gem-index.ts`）なので `sharedCache` のような
 * 可変状態の共有ではなく、**レジストリ別シャード（`D-38`）の再パースを毎リクエスト避ける**
 * ための使い回しに過ぎない（isolate 内メモリキャッシュは実装側が持つ）。
 */
const sharedGemIndexPort = new StaticGemIndex()

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
 * SP-5: 検索結果の取得（HIT/MISS の観測は `searchRepositoriesWithCacheStatus()` を使う）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で検索する（省略時は installation token）。
 */
export function searchRepositoriesUseCase(accessToken?: string | null): SearchRepositories {
  return makeSearchRepositories({ repos: makeCachingRepositoryQuery({ accessToken }) })
}

/**
 * SP-3: 独立 URL の詳細画面用ユースケースの組み立て（US-16 / US-17 / AC-4）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で取得する（省略時は installation token）。
 */
export function getRepositoryDetailUseCase(accessToken?: string | null): GetRepositoryDetail {
  return makeGetRepositoryDetail({ repos: makeCachingRepositoryQuery({ accessToken }) })
}

/**
 * Issue #334 F-4: 詳細画面の README 取得ユースケースの組み立て。
 * private ゲート（`findDetail` 経由）は usecase 内に埋め込み済み（`get-repository-readme.ts`）。
 * SP-8: `accessToken` を渡すとユーザー自身のレート枠で取得する（省略時は installation token）。
 */
export function getRepositoryReadmeUseCase(accessToken?: string | null): GetRepositoryReadme {
  return makeGetRepositoryReadme({ repos: makeCachingRepositoryQuery({ accessToken }) })
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
    search: makeSearchRepositories({ repos }),
    getCacheStatus: () => status,
  }
}

/**
 * SP-14: キーワード非依存の日次ダイジェスト（`ADR 0014`）。候補プールは静的 JSON
 * （`StaticGemDigest`・`D-28`）から読み、並べ替えは usecase 側で日付シードから決定論的に行う。
 * サーバー側に状態を持たない（`D-6` / `D-14`）ため、リクエストごとに使い捨てで組み立ててよい。
 */
export function getDailyDigestUseCase(): GetDailyDigest {
  return makeGetDailyDigest({ port: sharedGemDigestPort })
}

/**
 * SP-18: 検索結果カードへ出す Gem バッジの判定材料を引く（`D-36` / `D-38`）。
 * 見つからないリポジトリはキーに入らない。読み込みに失敗しても例外を投げず空 Map になる
 * （`GemIndexPort` の契約）ため、呼び出し側は「バッジが出ない」だけで済む。
 *
 * 🔴 **usecase を新設していない**（`makeSearchRepositories` 等と非対称に見えるのは意図的）。
 * ポートの `lookup()` をそのまま通すだけで、並べ替え・選定・閾値判定といったドメインの判断が
 * 1 つも無いため（`D-36`: 並び順は変えない）。1 箇所しか使わない抽象を先回りで足さない（YAGNI）。
 * ドメイン判断が生じた時点で `src/usecases/` へ切り出す。
 */
export function lookupGemIndexes(
  repositoryFullNames: readonly string[],
): Promise<ReadonlyMap<string, GemIndex>> {
  return sharedGemIndexPort.lookup(repositoryFullNames)
}

/**
 * SP-19: 検索語を引き継いだ Gem 一覧（`D-37` の照合規則）。
 *
 * 🔴 **`GemIndexPort` の実装を新しく `new` しない**（`sharedGemIndexPort` をそのまま使う）。
 * `StaticGemIndex` はレジストリ別シャード（計 3.5MB 弱・`D-38`）を isolate 内メモリへ載せる
 * singleton promise を持つため、ここで別インスタンスを作ると `SP-18` のバッジ経路と
 * キャッシュが分裂し、cold start のシャード取得が二重に走る。
 *
 * `lookupGemIndexes`（上）と違い **ユースケースを経由する**: 生の検索語をトークン列へ
 * 正規化するというドメイン規則の適用があるため（理由は `src/usecases/search-gems.ts` の JSDoc）。
 */
export function searchGemsUseCase(): SearchGems {
  return makeSearchGems({ gems: sharedGemIndexPort })
}
