import type { RateLimitDecision, RateLimitPort } from '../../domain/ports/rate-limit-port'

/**
 * Cloudflare Rate Limiting binding の最小形（cloudflare-infrastructure.md §3.3）。
 * 🔴 事業者固有バインディングの型・参照はこのファイル（src/infrastructure/platform/）に閉じる（NFR-21 / INF-5）。
 */
export interface RateLimiterBinding {
  limit(options: { key: string }): Promise<{ success: boolean }>
}

/** wrangler.jsonc の ratelimits[].simple.period と一致させる（60 秒）。 */
export const RATE_LIMIT_PERIOD_SECONDS = 60

/**
 * RATE_LIMITER binding のラッパー（`wrangler.jsonc` の `ratelimits` 宣言に対応）。
 * binding が未提供の環境（ローカル `npm test` 等・Cloudflare 実行環境の外）では、
 * 落ちずに「制限なし」を返すフォールバックにする。
 *
 * ⚠️ key は呼び出し側で HMAC 化した値を渡す（生 IP を渡さない・
 * cloudflare-infrastructure.md §9.1「Rate Limiting の key を HMAC 化する」）。本クラスは key の生成を行わない。
 */
export class WorkersRateLimit implements RateLimitPort {
  private readonly periodSeconds: number

  constructor(
    private readonly binding: RateLimiterBinding | undefined,
    options?: { periodSeconds?: number },
  ) {
    this.periodSeconds = options?.periodSeconds ?? RATE_LIMIT_PERIOD_SECONDS
  }

  async consume(key: string): Promise<RateLimitDecision> {
    if (!this.binding) {
      return { allowed: true }
    }
    // binding は事業者側の実行環境が注入する外部依存であり、型どおりの形が返る保証は実行時にはない。
    // 契約（RateLimitPort）が「consume は投げない」と約束しているため、undefined 等が返っても
    // プロパティ参照で TypeError を投げないよう `| undefined` として扱う。
    let result: { success: boolean } | undefined
    try {
      result = await this.binding.limit({ key })
    } catch {
      // binding が一時的にエラーを返した場合は「制限なし」を返す（fail-open）。
      // binding 未提供時のフォールバックと同じ扱いにする（RateLimitPort の契約）。
      return { allowed: true }
    }
    // 明示的に success: false と言われたときだけ拒否する。判定不能な形（undefined 等）は
    // 上の catch と同じく fail-open にする（レート制限は保護であって可用性の前提ではない）。
    if (result?.success === false) {
      // Cloudflare Rate Limiting binding の limit() は { success } しか返さず、次の窓が開く正確な時刻を
      // 教えてくれない。そのため wrangler.jsonc で宣言した period（＝窓の長さ）を
      // 「次の窓が開くまでの最大待ち時間」として Retry-After に使う（保守的な上限値）。
      return { allowed: false, retryAfterSeconds: this.periodSeconds }
    }
    return { allowed: true }
  }
}
