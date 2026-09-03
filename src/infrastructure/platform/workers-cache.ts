import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import type { ClockPort } from '../../domain/ports/clock-port'
import { InMemoryCache } from './cache'

/**
 * Cache API 上に合成するキーの疑似ホスト名（Issue #121）。
 * 実在するオリジンではなく、`CacheKey` を GET リクエスト URL へ写すための名前空間。
 */
export const CACHE_HOST = 'https://cache.gem-hunter.internal'

/** `WorkersCache.set` が本文へ書き込む内部形式。 */
interface CachePayload<T> {
  readonly value: T
  readonly expiresAt: number
}

/**
 * 残 TTL つきで読める `CachePort`（`TieredCache` の write-back のための任意拡張）。
 * `CachePort` 本体の面積は広げない（`NFR-17`）。
 */
export interface TtlAwareCache extends CachePort {
  /**
   * キャッシュを読み、残り TTL（秒・切り上げ）とあわせて返す。
   *
   * @returns 有効な値と残り TTL、未登録または残 TTL が 1 未満（期限切れ含む）なら `null`。
   * 🔴 異常時の振る舞いは `get` と同じく throw しない。
   */
  getWithTtl<T>(key: CacheKey): Promise<{ value: T; remainingTtlSeconds: number } | null>
}

/**
 * `caches` グローバル（Cloudflare Cache API）に `default` を追加した shape。
 * 標準 DOM の `CacheStorage` は `default` を持たないため、事業者拡張として明示する。
 * 🔴 事業者固有バインディングの型・参照はこのファイル（`src/infrastructure/platform/`）に閉じる（`ARCH-4`）。
 */
type CloudflareCacheStorage = CacheStorage & { readonly default?: Cache }

/**
 * `ttlSeconds` の値域検証（`CachePort` の契約どおり）。`WorkersCache` / `TieredCache` の
 * 両方から呼ぶため 1 箇所に切り出す（同じ判定を 2 か所に書かない）。
 */
function validateTtlSeconds(ttlSeconds: number): void {
  if (!Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
    throw new RangeError(
      `ttlSeconds は正の有限数である必要があります（受け取った値: ${ttlSeconds}）`,
    )
  }
}

/**
 * `caches.default`（Cloudflare Cache API の既定キャッシュ）を取得する。
 * `caches` グローバル自体が未定義の実行環境（本リポジトリのテスト・`next start` 等）や
 * `default` が生えていない環境では `undefined` を返す（fail-open・呼び出し側が no-op に倒す）。
 */
function resolveCache(): Cache | undefined {
  if (typeof caches === 'undefined') {
    return undefined
  }
  return (caches as CloudflareCacheStorage).default
}

function keyToUrl(key: CacheKey): string {
  return `${CACHE_HOST}/${encodeURIComponent(key)}`
}

/**
 * Cloudflare Cache API（`caches.default`）を `CachePort` として使う実装（Issue #121）。
 *
 * isolate（リクエストを処理する実行単位）をまたいでキャッシュを共有するための後段レイヤー。
 * `InMemoryCache`（isolate 内メモリのみ）と対になり、`TieredCache` の後段として使う想定。
 *
 * 🔴 **Cache API の制約**（Cloudflare 公式）: `cache.put()` は GET 以外の `Request` や、
 * `status 206` / `Vary: *` / `Set-Cookie` を持つ `Response` に対して例外を投げる。
 * 本実装が合成する `Request` は常に GET、`Response` は常に 200 かつ `Set-Cookie` なしにする。
 */
export class WorkersCache implements TtlAwareCache {
  private readonly clock: ClockPort

  constructor(options: { clock: ClockPort }) {
    this.clock = options.clock
  }

  async get<T>(key: CacheKey): Promise<T | null> {
    const entry = await this.readEntry<T>(key)
    return entry ? entry.value : null
  }

  async getWithTtl<T>(key: CacheKey): Promise<{ value: T; remainingTtlSeconds: number } | null> {
    return this.readEntry<T>(key)
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    // 🔴 caches が未定義でも検証は行う（黙って fail-open にしない・CachePort の契約）。
    validateTtlSeconds(ttlSeconds)

    const cache = resolveCache()
    if (!cache) {
      return
    }

    const expiresAt = this.clock.now().getTime() + ttlSeconds * 1000
    const payload: CachePayload<T> = { value, expiresAt }
    const response = new Response(JSON.stringify(payload), {
      status: 200,
      headers: {
        'Cache-Control': `max-age=${ttlSeconds}`,
        'Content-Type': 'application/json',
      },
    })
    const request = new Request(keyToUrl(key), { method: 'GET' })

    try {
      await cache.put(request, response)
    } catch {
      // キャッシュ書き込み失敗でアプリを止めない（no-op として握る）。
    }
  }

  async invalidate(key: CacheKey): Promise<void> {
    const cache = resolveCache()
    if (!cache) {
      return
    }
    try {
      await cache.delete(keyToUrl(key))
    } catch {
      // 冪等: delete の例外も throw しない。
    }
  }

  /**
   * `caches.default` から読み、有効なペイロードなら値と残 TTL を返す。
   * 未登録・パース失敗・残 TTL が 1 未満（期限切れ含む）・Cache API の例外、いずれも `null`。
   */
  private async readEntry<T>(
    key: CacheKey,
  ): Promise<{ value: T; remainingTtlSeconds: number } | null> {
    const cache = resolveCache()
    if (!cache) {
      return null
    }

    let response: Response | undefined
    try {
      response = await cache.match(keyToUrl(key))
    } catch {
      return null
    }
    if (!response) {
      return null
    }

    let payload: CachePayload<T>
    try {
      payload = (await response.json()) as CachePayload<T>
    } catch {
      return null
    }

    const remainingTtlSeconds = Math.ceil((payload.expiresAt - this.clock.now().getTime()) / 1000)
    if (remainingTtlSeconds < 1) {
      return null
    }
    return { value: payload.value, remainingTtlSeconds }
  }
}

function isTtlAwareCache(cache: CachePort): cache is TtlAwareCache {
  return typeof (cache as Partial<TtlAwareCache>).getWithTtl === 'function'
}

/**
 * 1 つの層から読む。`TtlAwareCache` なら **`getWithTtl` で 1 回だけ読む**
 * （write-back のために `get` → `getWithTtl` と 2 度読みすると、Cache API への往復が
 * 後段 HIT のたびに 2 倍になる）。残 TTL を返せない層では `remainingTtlSeconds` を
 * `null` にして返し、呼び出し側が write-back を行わない（誤った延命を避ける）。
 *
 * 🔴 層の読み取りで例外が出ても throw しない（`CachePort.get` の契約）。
 */
async function readLayer<T>(
  layer: CachePort,
  key: CacheKey,
): Promise<{ value: T; remainingTtlSeconds: number | null } | null> {
  try {
    if (isTtlAwareCache(layer)) {
      const entry = await layer.getWithTtl<T>(key)
      return entry === null
        ? null
        : { value: entry.value, remainingTtlSeconds: entry.remainingTtlSeconds }
    }
    const value = await layer.get<T>(key)
    return value === null ? null : { value, remainingTtlSeconds: null }
  } catch {
    return null
  }
}

/**
 * 複数の `CachePort` を前段 → 後段の順に引く合成実装（Issue #121）。
 *
 * `get` は前段から順に引き、非 `null` を返した層で確定する。後段（インデックス 1 以降）で
 * HIT した場合、その層が `getWithTtl` を持てば残 TTL つきで前段（HIT した層より前の全層）へ
 * write-back する（誤った延命を避けるため、`getWithTtl` を持たない層からは write-back しない）。
 */
export class TieredCache implements CachePort {
  constructor(private readonly layers: readonly CachePort[]) {}

  async get<T>(key: CacheKey): Promise<T | null> {
    for (let index = 0; index < this.layers.length; index += 1) {
      const layer = this.layers[index]!
      const entry = await readLayer<T>(layer, key)
      if (entry === null) {
        continue
      }
      if (index > 0 && entry.remainingTtlSeconds !== null) {
        await this.writeBackToPrecedingLayers(key, entry.value, entry.remainingTtlSeconds, index)
      }
      return entry.value
    }
    return null
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    // 🔴 先頭で 1 回だけ検証する（層ごとの二重検証に依存しない・不正なら全層へ書かず throw）。
    validateTtlSeconds(ttlSeconds)
    await Promise.all(this.layers.map((layer) => layer.set(key, value, ttlSeconds)))
  }

  async invalidate(key: CacheKey): Promise<void> {
    await Promise.all(this.layers.map((layer) => layer.invalidate(key)))
  }

  private async writeBackToPrecedingLayers<T>(
    key: CacheKey,
    value: T,
    remainingTtlSeconds: number,
    hitIndex: number,
  ): Promise<void> {
    for (let index = 0; index < hitIndex; index += 1) {
      try {
        await this.layers[index]!.set(key, value, remainingTtlSeconds)
      } catch {
        // write-back 失敗は読み取りを失敗させない。
      }
    }
  }
}

/**
 * composition root が呼ぶファクトリ。前段 = isolate 内メモリ（`InMemoryCache`）、
 * 後段 = isolate をまたいで共有される Cache API（`WorkersCache`）。
 */
export function createSharedCache(clock: ClockPort): CachePort {
  return new TieredCache([new InMemoryCache(clock), new WorkersCache({ clock })])
}
