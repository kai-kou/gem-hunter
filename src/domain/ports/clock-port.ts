/**
 * 現在時刻の取得口（テスト決定性・SD-2）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 * 面積はこれ以上広げない（`now(): Date` 1 本・YAGNI）。
 */
export interface ClockPort {
  /**
   * 現在時刻を返す。
   *
   * @returns 有効な `Date`（`getTime()` が有限数）。引数は取らない。
   *
   * 🔴 **異常時の振る舞い**: throw しない（実装は常に有効な `Date` を返す）。
   *   タイムゾーンは持たせない（表示側で JST に整形する・`datetime-rules.md`）。
   */
  now(): Date
}
