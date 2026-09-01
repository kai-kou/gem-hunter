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
   * @param key 空でない文字列。
   * @returns 有効期限内の値、未登録または期限切れなら `null`（期限切れは throw ではなく `null`）。
   *
   * 🔴 **異常時の振る舞い**: throw しない（ミスは全て `null` として表現する）。
   */
  get<T>(key: string): Promise<T | null>
  /**
   * キャッシュへ書く。
   *
   * @param key 空でない文字列。
   * @param value 任意の値（`undefined` も保持できる）。
   * @param ttlSeconds **正の有限数**（秒）。`0` / 負値 / `NaN` / `Infinity` は不正。
   *
   * 🔴 **異常時の振る舞い**: `ttlSeconds` が値域外なら `RangeError` を **throw する**
   *   （黙って無期限保持にしない＝fail-open を作らない・Issue #67 の是正）。
   */
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>
  /**
   * キャッシュを破棄する。
   *
   * @param key 空でない文字列。
   *
   * 🔴 **異常時の振る舞い**: 未登録の key でも throw せず正常終了する（冪等）。
   */
  invalidate(key: string): Promise<void>
}
