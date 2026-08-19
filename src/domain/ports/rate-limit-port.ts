/** レート制限の判定結果。`retryAfterSeconds` は拒否時のみ意味を持つ。 */
export type RateLimitDecision = {
  readonly allowed: boolean
  readonly retryAfterSeconds?: number
}

/**
 * レート制限の可否判定（INF-n / NFR-7）。
 * 実装は src/infrastructure/platform/ に置く。Cloudflare Rate Limiting binding が
 * 未提供の環境（ローカル `npm test` 等）では、落ちずに「制限なし」を返すフォールバックにする。
 */
export interface RateLimitPort {
  consume(key: string): Promise<RateLimitDecision>
}
