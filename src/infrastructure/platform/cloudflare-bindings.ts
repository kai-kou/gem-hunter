import type { RateLimiterBinding } from './rate-limit'

/**
 * `@opennextjs/cloudflare` が公開する env の型（`declare global` で `CloudflareEnv` を拡張する形）。
 * `RATE_LIMITER` は本プロジェクトの `wrangler.jsonc` の `ratelimits` 宣言（カスタムバインディング）で
 * 追加されるものであり、パッケージ側の `CloudflareEnv` 型定義には含まれない。そのためここで
 * 最小限の shape を自前定義し、実行時の env に対して安全にアクセスする。
 */
type EnvWithRateLimiter = {
  RATE_LIMITER?: RateLimiterBinding
  /** SP-16 争点6: `sort=gemIndex` 専用の別スロット（`wrangler.jsonc` の低い上限のエントリ）。 */
  RATE_LIMITER_GEM_INDEX?: RateLimiterBinding
}

async function bindingOf(
  name: keyof EnvWithRateLimiter,
): Promise<RateLimiterBinding | undefined> {
  try {
    const { getCloudflareContext } = await import('@opennextjs/cloudflare')
    const context = await getCloudflareContext({ async: true })
    const env = context?.env as EnvWithRateLimiter | undefined
    return env?.[name]
  } catch {
    return undefined
  }
}

/**
 * Rate Limiting binding（`env.RATE_LIMITER`）を取得する。
 * Workers 実行環境の外（ローカル `npm test` / `next dev` 実行時等）や binding 未宣言の環境では
 * `getCloudflareContext()` が例外を投げるため、try/catch で undefined に倒す（フェイルオープン）。
 * これは「握り潰し」ではなく「binding 未提供」という正常系（`WorkersRateLimit` 側が undefined を
 * 受け取ったときに「制限なし」へフォールバックする設計に対応する）。
 *
 * 🔴 動的 import にする理由: `@opennextjs/cloudflare` は Workers 実行環境を前提としたモジュールで、
 * その環境の外（`npm test` 実行時の Node/jsdom 等）ではモジュール解決自体が失敗しうる。トップレベルの
 * 静的 import にすると、この関数を呼ばないテストまで巻き添えで壊れるため、呼び出し時にのみ動的 import する。
 */
export async function rateLimiterBinding(): Promise<RateLimiterBinding | undefined> {
  return bindingOf('RATE_LIMITER')
}

/**
 * SP-16 争点6: `sort=gemIndex` 専用の別スロット（`wrangler.jsonc` の `RATE_LIMITER_GEM_INDEX`）。
 * `sort=gemIndex` は 1 検索が最大 10 回の upstream 呼び出しになるため（全件取得）、
 * 通常枠（`RATE_LIMITER`）とは別に低い上限で消費させる（`src/composition/rate-limit.ts` 側で選択）。
 */
export async function gemIndexRateLimiterBinding(): Promise<RateLimiterBinding | undefined> {
  return bindingOf('RATE_LIMITER_GEM_INDEX')
}
