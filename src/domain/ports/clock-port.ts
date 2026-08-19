/**
 * 現在時刻の取得口（テスト決定性・SD-2）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 * 面積はこれ以上広げない（`now(): Date` 1 本・YAGNI）。
 */
export interface ClockPort {
  now(): Date
}
