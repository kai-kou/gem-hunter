import type { RateLimiterBinding } from './rate-limit'

/**
 * `@opennextjs/cloudflare` が公開する env の型（`declare global` で `CloudflareEnv` を拡張する形）。
 * `RATE_LIMITER` は本プロジェクトの `wrangler.jsonc` の `ratelimits` 宣言（カスタムバインディング）で
 * 追加されるものであり、パッケージ側の `CloudflareEnv` 型定義には含まれない。そのためここで
 * 最小限の shape を自前定義し、実行時の env に対して安全にアクセスする。
 */
type EnvWithRateLimiter = {
  RATE_LIMITER?: RateLimiterBinding
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
  try {
    const { getCloudflareContext } = await import('@opennextjs/cloudflare')
    const context = await getCloudflareContext({ async: true })
    const env = context?.env as EnvWithRateLimiter | undefined
    return env?.RATE_LIMITER
  } catch {
    return undefined
  }
}

/**
 * リクエストが処理された Cloudflare のコロケーションコード（例: `SJC` / `NRT`）。
 *
 * 🔴 **なぜ `cf-ray` ヘッダをパースしないのか（Issue #875 の実機欠陥・修正）**: 当初は着信
 * リクエストの `cf-ray` ヘッダから抽出する実装だったが、プレビュー実機（`pr-1059`）で
 * `request.headers.get('cf-ray')` が常時 `null` だった。`cf-ray` は Cloudflare が **レスポンスへ**
 * 付与するヘッダであり、Worker への着信リクエストヘッダとしては読めない（実測で判明）。
 * `getCloudflareContext().cf.colo` が着信リクエストの `cf` プロパティ経由でコロケーションコード
 * そのものを持つため、こちらを正とする（`rateLimiterBinding()` と同じ取得パターンを踏襲）。
 *
 * `getCloudflareContext()` は Workers 実行環境の外（`npm test` / `next dev` で
 * `initOpenNextCloudflareForDev` 未実施等）や `cf` 未提供の環境では例外を投げる、または
 * `cf` が無い場合があるため、try/catch で `undefined` に倒す（フェイルオープン・
 * 呼び出し側はヘッダを付けないだけでリクエストを壊さない）。
 */
export async function cloudflareColo(): Promise<string | undefined> {
  try {
    const { getCloudflareContext } = await import('@opennextjs/cloudflare')
    // `IncomingRequestCfProperties`（`@cloudflare/workers-types`）に依存せず、
    // `EnvWithRateLimiter` と同じ流儀で必要な最小限の shape だけを自前定義する。
    const context = await getCloudflareContext<{ colo?: string }>({ async: true })
    return context?.cf?.colo
  } catch {
    return undefined
  }
}
