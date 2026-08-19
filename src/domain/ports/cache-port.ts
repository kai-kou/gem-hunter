/**
 * キャッシュ抽象（NFR-17）。面積は get / set / invalidate + TTL のみに絞る
 * （YAGNI の意図的な例外・汎用キャッシュライブラリを自作しない）。
 * 実装は src/infrastructure/platform/ に置き、composition root で束ねる。
 *
 * ⚠️ **Issue #67「Cache Port の器」の範囲**: ここに定義するのはポートの契約のみ。
 * TTL 値の確定・レスポンスへの `Cache-Control` 適用（実適用）は `E-3` / `SP-5` のスコープ。
 */
export interface CachePort {
  get<T>(key: string): Promise<T | null>
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>
  invalidate(key: string): Promise<void>
}
