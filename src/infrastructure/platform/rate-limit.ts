import type { RateLimitDecision, RateLimitPort } from '../../domain/ports/rate-limit-port'

/**
 * Cloudflare Rate Limiting binding の最小形（cloudflare-infrastructure.md §3.3）。
 * 🔴 事業者固有バインディングの型・参照はこのファイル（src/infrastructure/platform/）に閉じる（NFR-21 / INF-5）。
 */
export interface RateLimiterBinding {
  limit(options: { key: string }): Promise<{ success: boolean }>
}

/**
 * RATE_LIMITER binding のラッパー（`wrangler.jsonc` の `ratelimits` 宣言に対応）。
 * binding が未提供の環境（ローカル `npm test` 等・Cloudflare 実行環境の外）では、
 * 落ちずに「制限なし」を返すフォールバックにする。
 *
 * ⚠️ key は呼び出し側で HMAC 化した値を渡す（生 IP を渡さない・
 * cloudflare-infrastructure.md §9.1「Rate Limiting の key を HMAC 化する」）。本クラスは key の生成を行わない。
 */
export class WorkersRateLimit implements RateLimitPort {
  constructor(private readonly binding: RateLimiterBinding | undefined) {}

  async consume(key: string): Promise<RateLimitDecision> {
    if (!this.binding) {
      return { allowed: true }
    }
    const result = await this.binding.limit({ key })
    // Cloudflare Rate Limiting binding の limit() は { success } しか返さないため retryAfterSeconds は設定しない
    return { allowed: result.success }
  }
}
