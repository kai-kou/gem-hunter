import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import { assertPositiveTtlSeconds } from './ttl'

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
 * キャッシュ値の封筒。
 *
 * - `ok`: **封筒であることの判別マーカー**。これが無いと `{"foo":1}` のような別スキーマの
 *   本文が `typeof === 'object'` を通過して `.value === undefined` になり、MISS ではなく
 *   「`undefined` を保存済み」として HIT 扱いされる（`LayeredCache` が primary へ充填し、
 *   `CachingRepositoryQuery` が `undefined` を `SearchResult` として返して `TypeError` になる）。
 * - `value`: 値を 1 段包むのは **`undefined` を往復させるため**。`JSON.stringify(undefined)` は
 *   `undefined`（文字列にならない）を返すので値を直接直列化できないが、
 *   `JSON.stringify({ ok: true, value: undefined })` は `'{"ok":true}'` になり、読み戻すと
 *   `envelope.value === undefined` として復元できる（`CachePort` は `undefined` の保持を要求する）。
 */
type CacheEnvelope = { ok: true; value?: unknown }

/**
 * `Date` を封筒の中で自己記述させるためのタグ。`{ '@d': '2026-01-01T00:00:00.000Z' }` の形で
 * 直列化し、読み戻し時に `Date` へ復元する。
 *
 * 🔴 **なぜ必要か（実測の障害）**: `JSON.parse` は `Date` を復元しないため、素朴に往復させると
 * `SearchResult.items[].lastPushedAt` / `RepositoryDetail.lastPushedAt` が **ISO 文字列のまま
 * `Date` を名乗って** 返る。2 段目（Cache API）HIT の経路でだけ `src/ui/repository-list.tsx` の
 * `Intl.DateTimeFormat#format()` が `RangeError: Invalid time value` を投げ、ページが 500 になる
 * （1 段目 `InMemoryCache` は値をそのまま保持するので同じ壊れ方をしない）。
 */
const DATE_TAG = '@d'

/**
 * `JSON.stringify` の replacer。`Date` をタグ付きオブジェクトへ写す。
 *
 * 🔴 `value` ではなく `this[key]`（＝ **加工前の値**）を見る: `JSON.stringify` は replacer を
 * 呼ぶ **前** に `Date#toJSON()` を適用するため、`value` の時点では既に ISO 文字列になっており
 * `instanceof Date` で判別できない。
 *
 * ⚠️ **Invalid Date**（`new Date('x')`）は `toISOString()` が throw するため `null` にする。
 * ここで throw させると封筒全体の直列化が失敗し、**その 1 フィールドのせいでエントリ全体が
 * キャッシュされなくなる**（`set` は throw しないが no-op になる）。壊れた日時 1 個の代償として
 * 過大なので、`JSON.stringify(new Date('x'))` の既定挙動（`null`）に合わせる。
 */
const replacer = function (this: Record<string, unknown>, key: string, value: unknown): unknown {
  const raw = this[key]
  if (raw instanceof Date) {
    return Number.isNaN(raw.getTime()) ? null : { [DATE_TAG]: raw.toISOString() }
  }
  return value
}

/**
 * `JSON.parse` の reviver。`replacer` が付けたタグを `Date` へ戻す。
 *
 * ⚠️ 素の値が偶然 `@d` というキーを持っていた場合も `Date` として復元される。本プロジェクトの
 * キャッシュ値（`SearchResult` / `RepositoryDetail` / README 文字列）はこのキーを持たない。
 */
const reviver = (_key: string, value: unknown): unknown =>
  value !== null && typeof value === 'object' && DATE_TAG in (value as object)
    ? new Date((value as Record<string, string>)[DATE_TAG]!)
    : value

/**
 * `Cache-Control: max-age` に書ける上限（秒・1 年）。
 *
 * 🔴 上限が無いと `1e21` のような巨大値が `Math.floor` を素通りし、テンプレート展開で
 * `max-age=1e+21` という **不正な delta-seconds**（RFC 9111 は 1 個以上の数字だけを許す）に
 * なる。受け側の解釈は実装依存（0 とみなす＝即時失効、あるいはヘッダごと無視）で、
 * どちらに転んでも「書いたのに効かない」無音の劣化になる。
 */
const MAX_AGE_CAP_SECONDS = 31_536_000

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
 * 連続リクエストの HIT 率が低いことを実測した（数値は ADR 0016 §1.1 が正本）。Cache API は
 * コロケーション単位で共有され、
 * isolate のリサイクルに影響されない。
 *
 * TTL は Cache API 自身が `Cache-Control: max-age` を解釈して管理するため、本クラスは
 * `ClockPort` を持たない（`InMemoryCache` と異なり期限判定を自前で行わない）。
 *
 * 契約（`cache-port.ts`）の遵守:
 * - `get` は throw しない（MISS・期限切れ・Cache API の失敗・壊れた本文はすべて `null`）
 * - `set` は `ttlSeconds` が正の有限数でなければ `RangeError`（fail-open を作らない）
 * - `invalidate` は未登録キーでも throw しない（冪等）
 *
 * 🔴 **往復できる値の範囲（JSON + 封筒の制約・呼び出し側が知っておくべき前提）**:
 * - `Date` → **往復する**（`DATE_TAG` 付きオブジェクトへ写して復元する。Invalid Date のみ `null`）
 * - `undefined` / `null` → 往復する（封筒の `value` で区別する）
 * - `NaN` / `Infinity` / `-Infinity` → **`null` になる**（`JSON.stringify` の仕様）
 * - `Map` / `Set` → **`{}` になる**（列挙可能な自前プロパティを持たないため中身が消える）
 * - `BigInt` → `JSON.stringify` が `TypeError` を投げるため **キャッシュされない**（`set` は no-op）
 * - 関数・`Symbol` → プロパティごと消える
 * - 循環参照 → `TypeError` を投げるため **キャッシュされない**（`set` は no-op・throw しない）
 *
 * `InMemoryCache`（1 段目）は値をそのまま保持するのでこれらの制約が無い。**両段で同じ値が
 * 返ることを前提にしてよいのは上記の範囲だけ**（`SearchResult` / `RepositoryDetail` /
 * README 文字列は全てこの範囲に収まる）。
 */
export class WorkersCache implements CachePort {
  /**
   * 既に警告済みの操作名。**isolate（＝このインスタンス）ごとに 1 回だけ** 警告する
   * （毎リクエスト出すとログが埋まる）。
   */
  private readonly warnedOperations = new Set<string>()

  constructor(private readonly storage: WorkersCacheStorage) {}

  async get<T>(key: CacheKey): Promise<T | null> {
    let response: Response | undefined
    try {
      response = await this.storage.match(cacheKeyToRequest(key))
    } catch (error) {
      // Cache API の一時障害は「キャッシュに無かった」と同義に倒す（キャッシュは可用性の前提
      // ではない）。ただし **無音にはしない**（下の `warnOnce` の JSDoc 参照）。
      this.warnOnce('match', error)
      return null
    }
    if (!response) {
      return null
    }
    try {
      const parsed: unknown = JSON.parse(await response.text(), reviver)
      if (
        typeof parsed !== 'object' ||
        parsed === null ||
        (parsed as Partial<CacheEnvelope>).ok !== true
      ) {
        // 想定の封筒形でない（別スキーマ・別用途のエントリ）。MISS として扱う。
        return null
      }
      return (parsed as CacheEnvelope).value as T
    } catch {
      // 本文の破損（JSON として壊れている）も MISS。Cache API 自体は生きているので警告しない。
      return null
    }
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    // ⚠️ TTL 検証は下の try の **外** に置くこと。中に入れると不正 TTL が握り潰されて
    // fail-open になる。
    assertPositiveTtlSeconds(ttlSeconds)
    // `max-age` は整数秒（delta-seconds）。1 秒未満の TTL は 0 に潰す（＝即時失効）のではなく
    // 1 秒へ切り上げ、巨大値は `MAX_AGE_CAP_SECONDS` でクランプして指数表記を作らない。
    const maxAge = Math.min(MAX_AGE_CAP_SECONDS, Math.max(1, Math.floor(ttlSeconds)))
    let body: string
    try {
      body = JSON.stringify({ ok: true, value } satisfies CacheEnvelope, replacer)
    } catch {
      // 循環参照など直列化できない値。キャッシュできなかっただけで、呼び出し側は取得済みの
      // 値をそのまま返せる（Cache API の障害ではないので警告しない）。
      return
    }
    try {
      const response = new Response(body, {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': `max-age=${maxAge}`,
        },
      })
      await this.storage.put(cacheKeyToRequest(key), response)
    } catch (error) {
      // Cache API の書き込み失敗でリクエスト本体を壊さない。
      this.warnOnce('put', error)
    }
  }

  async invalidate(key: CacheKey): Promise<void> {
    try {
      await this.storage.delete(cacheKeyToRequest(key))
    } catch (error) {
      // 未登録キー・Cache API の失敗いずれも throw しない（冪等の契約）。
      this.warnOnce('delete', error)
    }
  }

  /**
   * Cache API の失敗を isolate ごと 1 回だけ表明する（`[rate-limit]` / `[AssetReader]` と同じ流儀）。
   *
   * 🔴 **なぜ必要か**: 例外を痕跡なく握り潰すと「`caches` は存在するが `put` が常に拒否される」
   * 状態（`ADR 0016` §5.4 が未確定として挙げたリスク）が本番で起きても、2 段目が丸ごと no-op に
   * なったことを外から観測できない（HIT 率が落ちるだけで原因が分からない）。
   *
   * ⚠️ **キー・値は出さない**（キャッシュキーは検索語を含み、値は API レスポンス本体）。
   * 出すのは操作名と例外オブジェクトだけ。
   */
  private warnOnce(operation: 'put' | 'match' | 'delete', error: unknown): void {
    if (this.warnedOperations.has(operation)) {
      return
    }
    this.warnedOperations.add(operation)
    console.warn(
      `[cache] Cache API の ${operation} に失敗しました（2 段目が no-op になっています・以降は抑制）`,
      error,
    )
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
