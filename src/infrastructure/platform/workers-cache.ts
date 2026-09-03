import type { CacheKey, CachePort } from '../../domain/ports/cache-port'

/**
 * Cloudflare Cache API（`caches.default`）の最小形。
 *
 * 🔴 事業者固有 API の型・参照はこのファイル（`src/infrastructure/platform/`）に閉じる
 * （`ARCH-4` / `NFR-21` / `INF-5`）。`WorkersRateLimit` の `RateLimiterBinding` と同じ流儀で、
 * 実際に使う 3 メソッドだけを自前で型定義し、`@cloudflare/workers-types` に依存しない。
 */
export interface WorkersCacheStorage {
  put(request: Request, response: Response): Promise<void>
  match(request: Request): Promise<Response | undefined>
  delete(request: Request): Promise<boolean>
}

/**
 * `CacheKey` を写す先の固定オリジン。
 *
 * Cache API のキーは `Request`（＝ URL）であり、`CacheKey` はそのままでは URL ではない。
 * 実在しない専用オリジン配下のパスへ写すことで、① 実サイトの URL（`/ja/repos/...` 等）と
 * 名前空間が衝突しない ② コロケーション内で他の用途のエントリと混ざらない、を同時に満たす。
 */
export const CACHE_KEY_ORIGIN = 'https://cache.gem-hunter.internal/'

/**
 * キャッシュ値の封筒。`value` を 1 段包むのは **`undefined` を往復させるため**。
 * `JSON.stringify(undefined)` は `undefined`（文字列にならない）を返すので値を直接
 * 直列化できないが、`JSON.stringify({ value: undefined })` は `'{}'` になり、読み戻すと
 * `envelope.value === undefined` として復元できる（`CachePort` は `undefined` の保持を要求する）。
 */
type CacheEnvelope = { value?: unknown }

/**
 * `CacheKey` を Cache API のキー（`Request`）へ写す。
 *
 * 🔴 **`encodeURIComponent` を必ず通す**: キーは `search:v2:owner/name:page=1` のように
 * `:` `/` `=` を含み、生のまま連結すると `?` `#` を含むキーでクエリ・フラグメントが生えて
 * 別キーと同じ URL へ潰れる（衝突）ほか、空白等で不正な URL になる。エンコードすれば
 * キー文字列と URL パスが 1 対 1 に対応する。
 */
export function cacheKeyToRequest(key: CacheKey): Request {
  return new Request(`${CACHE_KEY_ORIGIN}${encodeURIComponent(key)}`)
}

/**
 * `CachePort` の Cloudflare Cache API 実装（Issue #121）。
 *
 * **なぜ必要か（実測）**: `InMemoryCache` は composition root のモジュールスコープ singleton
 * だが、Workers はリクエストを複数 isolate へ分散するため、プレビュー実測で同一 URL 12 回
 * 連続リクエストの HIT が 2 回（≒17%）しかなかった。Cache API はコロケーション単位で共有され、
 * isolate のリサイクルに影響されない。
 *
 * TTL は Cache API 自身が `Cache-Control: max-age` を解釈して管理するため、本クラスは
 * `ClockPort` を持たない（`InMemoryCache` と異なり期限判定を自前で行わない）。
 *
 * 契約（`cache-port.ts`）の遵守:
 * - `get` は throw しない（MISS・期限切れ・Cache API の失敗・壊れた本文はすべて `null`）
 * - `set` は `ttlSeconds` が正の有限数でなければ `RangeError`（fail-open を作らない）
 * - `invalidate` は未登録キーでも throw しない（冪等）
 */
export class WorkersCache implements CachePort {
  constructor(private readonly storage: WorkersCacheStorage) {}

  async get<T>(key: CacheKey): Promise<T | null> {
    try {
      const response = await this.storage.match(cacheKeyToRequest(key))
      if (!response) {
        return null
      }
      const parsed: unknown = JSON.parse(await response.text())
      if (typeof parsed !== 'object' || parsed === null) {
        // 想定の封筒形でない（別スキーマ・別用途のエントリ）。MISS として扱う。
        return null
      }
      return (parsed as CacheEnvelope).value as T
    } catch {
      // Cache API の一時障害・本文の破損は「キャッシュに無かった」と同義に倒す
      // （キャッシュは可用性の前提ではない）。
      return null
    }
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    if (!Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
      throw new RangeError(
        `ttlSeconds は正の有限数である必要があります（受け取った値: ${ttlSeconds}）`,
      )
    }
    // `max-age` は整数秒（delta-seconds）。1 秒未満の TTL は 0 に潰す（＝即時失効）のではなく
    // 1 秒へ切り上げる（`set` したのに必ず MISS になる挙動を作らない）。
    const maxAge = Math.max(1, Math.floor(ttlSeconds))
    try {
      const body = JSON.stringify({ value } satisfies CacheEnvelope)
      const response = new Response(body, {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': `max-age=${maxAge}`,
        },
      })
      await this.storage.put(cacheKeyToRequest(key), response)
    } catch {
      // 直列化不能な値・Cache API の書き込み失敗でリクエスト本体を壊さない
      // （キャッシュできなかっただけで、呼び出し側は取得済みの値をそのまま返せる）。
      // ⚠️ TTL 検証（`RangeError`）はこの try の **外** に置くこと。中に入れると
      // 不正 TTL が握り潰されて fail-open になる。
    }
  }

  async invalidate(key: CacheKey): Promise<void> {
    try {
      await this.storage.delete(cacheKeyToRequest(key))
    } catch {
      // 未登録キー・Cache API の失敗いずれも throw しない（冪等の契約）。
    }
  }
}

/**
 * 実行時に `caches.default`（Cloudflare Cache API）が使えるかを判定して返す。
 *
 * - Workers 実行環境: `caches.default` があるのでそれを返す
 * - Node / Vitest / ビルド時: `caches` 自体が無いので `undefined`
 * - ブラウザ相当（jsdom 等）: `caches` はあっても `default` を持たないので `undefined`
 *
 * 判定は「メソッドが 3 つ揃っているか」まで行う（`caches` という名前だけを見て
 * `WorkersCache` を組み立てると、実行時に `put is not a function` で落ちる）。
 */
export function workersCacheStorage(): WorkersCacheStorage | undefined {
  const cacheStorage = (globalThis as { caches?: { default?: unknown } }).caches
  const candidate = cacheStorage?.default as Partial<WorkersCacheStorage> | undefined
  if (
    !candidate ||
    typeof candidate.put !== 'function' ||
    typeof candidate.match !== 'function' ||
    typeof candidate.delete !== 'function'
  ) {
    return undefined
  }
  return candidate as WorkersCacheStorage
}
