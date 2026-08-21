import { RateLimitExceededError } from '../domain/errors'
import {
  gemIndexRateLimiterBinding,
  rateLimiterBinding,
} from '../infrastructure/platform/cloudflare-bindings'
import { clientIpOf, hashRateLimitKey } from '../infrastructure/platform/rate-limit-key'
import { RATE_LIMIT_PERIOD_SECONDS, WorkersRateLimit } from '../infrastructure/platform/rate-limit'

/**
 * composition root（Issue #122）。検索経路（画面 / GET /api/search）の自リクエスト間引きを
 * `RateLimitPort`（`WorkersRateLimit`）へ実際に配線する唯一の場所。
 * 検索・詳細取得の組み立て（`container.ts`）や認証（`auth.ts`）と同じく、composition root を
 * 関心ごとにファイルへ分けている（`src/composition/` 配下全体が composition root・architecture §2.1）。
 */

/**
 * 検索経路の自リクエスト間引き（Issue #122 / NFR-7）。超過時は
 * `RateLimitExceededError('rateLimitSecondary')` を投げる。
 *
 * 判定できない事情（接続元不明・salt 未設定・binding 未提供）があれば **フェイルオープン**（黙って通す）。
 * これは「握り潰し」ではなく、設定不備や実行環境の違いでサービス全体を止めないための意図的な設計判断。
 *
 * 🔴 **SP-16 争点6**: `sort` は「早期パース済みの `SortOrder`（または未指定）」を呼び出し側
 * （`app/api/search/route.ts` / `app/[locale]/page.tsx`）から渡す。`sort === 'gemIndex'` の
 * 検索は最大 1,000 件（`per_page=100` × 最大 10 ページ）を取得するため 1 検索が最大 10 回の
 * upstream 呼び出しになり、通常検索と同じ枠（`RATE_LIMITER`）で数えると単一クライアントが
 * 共有枠を最大 10 倍消費できてしまう（whiteboard round3 lead 裁定）。そのため
 * `sort === 'gemIndex'` のときだけ別スロット（`gemIndexRateLimiterBinding` /
 * `wrangler.jsonc` の `RATE_LIMITER_GEM_INDEX`・低い上限）・別名前空間のキーで消費し、
 * 通常枠とは独立に間引く。`WorkersRateLimit` 自体・通常枠の挙動は変えない（加算的変更）。
 */
export async function enforceSearchRateLimit(headers: Headers, sort?: string): Promise<void> {
  // 1. 接続元 IP を識別できない（Workers 実行環境の外・ヘッダ欠落等）場合は、
  //    そもそも誰を制限すべきか判定できないため間引かない。
  const ip = clientIpOf(headers)
  if (ip === null) {
    return
  }

  // 2. salt が未設定 / 空なら鍵を作れない。ここで生 IP をキーにすると
  //    cloudflare-infrastructure.md §9.1 の HMAC 化要件に反し、かといって salt なしで
  //    固定文字列をキーにすると全利用者が 1 つのキーを共有して過剰に制限し合う。
  //    どちらも避けるため、この環境（salt 未設定）では間引かない。
  const salt = process.env.RATE_LIMIT_SALT
  if (!salt) {
    return
  }

  const isGemIndexSort = sort === 'gemIndex'

  // 3. binding 未提供環境（ローカル `npm test` / Cloudflare 実行環境の外）では
  //    そもそも Cloudflare Rate Limiting を呼びようがないため間引かない
  //    （`WorkersRateLimit` 自体も binding undefined でフェイルオープンするが、
  //    ここで早期 return してハッシュ化コストも避ける）。
  const binding = await (isGemIndexSort ? gemIndexRateLimiterBinding() : rateLimiterBinding())
  if (!binding) {
    return
  }

  // gemIndex 専用スロットは通常枠と名前空間を分け、枠を共有しない（争点6）。
  const keyNamespace = isGemIndexSort ? 'search-gem-index' : 'search'
  const key = `${keyNamespace}:${await hashRateLimitKey(ip, salt)}`
  const limiter = new WorkersRateLimit(binding, { periodSeconds: RATE_LIMIT_PERIOD_SECONDS })
  const decision = await limiter.consume(key)

  if (!decision.allowed) {
    // 自リクエストの間引きは「短時間の集中により一定時間後に再試行できる」性質であり、
    // prd.md §7 の二次レート制限（`retry-after` 秒後に再試行可能と提示）の定義と一致する。
    // 一次レート制限（枠の枯渇・復帰時刻提示）とは性質が異なるため、新しい ErrorKind や
    // メッセージカタログを増やさず既存の `rateLimitSecondary` を再利用する。
    throw new RateLimitExceededError('rateLimitSecondary', {
      retryAfterSeconds: decision.retryAfterSeconds,
    })
  }
}
