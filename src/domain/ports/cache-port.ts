declare const cacheKeyBrand: unique symbol

/**
 * 名前空間つき・正規化済みのキャッシュキー（`NFR-18`）。
 *
 * 🔴 **このブランド型はポートの契約そのもの**（`CachePort` の呼び出し側が生成関数を経ない
 * 文字列を渡すことをコンパイル時に防ぐための型・Issue #89）。実際のキー生成（正規化・
 * 名前空間・スキーマバージョンの組み立て）は `src/infrastructure/platform/cache-key.ts`
 * に置く（`CachePort` の実装と同じ層。キー形式が実装詳細と不可分なため・
 * `domain-model.md` §4）。domain はこの型を **定義するだけ** で構築しない
 * （ARCH-1: domain は infrastructure を import できないため、生成関数は infra 側のまま）。
 */
export type CacheKey = string & { readonly [cacheKeyBrand]: 'CacheKey' }

/**
 * キャッシュ抽象（NFR-17）。面積は get / set / invalidate + TTL のみに絞る
 * （YAGNI の意図的な例外・汎用キャッシュライブラリを自作しない）。
 * 実装は src/infrastructure/platform/ に置き、composition root で束ねる。
 *
 * ⚠️ **Issue #67「Cache Port の器」の範囲**: ここに定義するのはポートの契約のみ。
 * TTL 値の確定・レスポンスへの `Cache-Control` 適用（実適用）は `E-3` / `SP-5` のスコープ。
 */
export interface CachePort {
  /**
   * キャッシュを読む。
   *
   * @param key `CacheKey`（`src/infrastructure/platform/cache-key.ts` の生成関数以外で
   *   組み立てない・Issue #89）。
   * @returns 有効期限内の値、未登録または期限切れなら `null`（期限切れは throw ではなく `null`）。
   *
   * 🔴 **異常時の振る舞い**: throw しない（ミスは全て `null` として表現する）。
   */
  get<T>(key: CacheKey): Promise<T | null>
  /**
   * キャッシュへ書く。
   *
   * @param key `CacheKey`（`src/infrastructure/platform/cache-key.ts` の生成関数以外で
   *   組み立てない・Issue #89）。
   * @param value 任意の値（`undefined` も保持できる）。
   * @param ttlSeconds **正の有限数**（秒）。`0` / 負値 / `NaN` / `Infinity` は不正。
   *
   * 🔴 **異常時の振る舞い**: `ttlSeconds` が値域外なら `RangeError` を **throw する**
   *   （黙って無期限保持にしない＝fail-open を作らない・Issue #67 の是正）。
   */
  set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void>
  /**
   * キャッシュを破棄する。
   *
   * @param key `CacheKey`（`src/infrastructure/platform/cache-key.ts` の生成関数以外で
   *   組み立てない・Issue #89）。
   *
   * 🔴 **異常時の振る舞い**: 未登録の key でも throw せず正常終了する（冪等）。
   */
  invalidate(key: CacheKey): Promise<void>
}
