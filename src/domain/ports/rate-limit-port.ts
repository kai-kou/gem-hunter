/** レート制限の判定結果。`retryAfterSeconds` は拒否時のみ意味を持つ。 */
export type RateLimitDecision = {
  readonly allowed: boolean
  /** 拒否時に再試行までの待ち時間として使う秒数（正の有限数）。許可時は付けない。 */
  readonly retryAfterSeconds?: number
}

/**
 * レート制限の可否判定（INF-n / NFR-7）。
 * 実装は src/infrastructure/platform/ に置く。
 */
export interface RateLimitPort {
  /**
   * 1 リクエスト分を消費して可否を返す。
   *
   * @param key 判定単位の識別子（空でない文字列）。**呼び出し側で HMAC 化した値を渡す**
   *   （生 IP を渡さない・cloudflare-infrastructure.md §9.1）。
   * @returns 許可なら `{ allowed: true }`、拒否なら `{ allowed: false, retryAfterSeconds }`。
   *
   * 🔴 **異常時の振る舞い（fail-open・throw しない）**: 実装は以下のいずれでも例外を伝播させず
   * `{ allowed: true }` を返す。レート制限は保護であって可用性の前提ではないため、
   * 判定基盤の一時障害でサービス全体を落とさない。
   * - Cloudflare Rate Limiting binding が未提供の環境（ローカル `npm test` 等）
   * - binding の呼び出しが reject / throw した場合
   */
  consume(key: string): Promise<RateLimitDecision>
}
