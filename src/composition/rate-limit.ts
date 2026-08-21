import { RateLimitExceededError } from '../domain/errors'
import { rateLimiterBinding } from '../infrastructure/platform/cloudflare-bindings'
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
 * 🔴 **`cost`（PR #293 セルフレビュー指摘・修正②・レート増幅対策）**: `sort=gem-index` は
 * 1 リクエストで最大 `GEM_INDEX_FETCH_MAX_PAGES` 回の上流呼び出しに増幅するため、既定の
 * 「1 リクエスト = 1 消費」のままだと同一 IP から少数回叩くだけで共有枠を単独で使い切れる。
 * 呼び出し側（`app/[locale]/page.tsx` / `app/api/search/route.ts`）が `sort=gem-index` のときだけ
 * `cost` に取得予定ページ数の上限を渡し、その回数だけ `limiter.consume` を呼ぶ。1 回でも
 * 拒否されたら残りは消費せず即座に例外を投げる（フェイルオープンの既存方針は変えない）。
 */
export async function enforceSearchRateLimit(
  headers: Headers,
  options?: { cost?: number },
): Promise<void> {
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

  // 3. binding 未提供環境（ローカル `npm test` / Cloudflare 実行環境の外）では
  //    そもそも Cloudflare Rate Limiting を呼びようがないため間引かない
  //    （`WorkersRateLimit` 自体も binding undefined でフェイルオープンするが、
  //    ここで早期 return してハッシュ化コストも避ける）。
  const binding = await rateLimiterBinding()
  if (!binding) {
    return
  }

  const key = `search:${await hashRateLimitKey(ip, salt)}`
  const limiter = new WorkersRateLimit(binding, { periodSeconds: RATE_LIMIT_PERIOD_SECONDS })
  const cost = options?.cost ?? 1

  // 🔴 逐次消費（並列にしない）: 1 回でも拒否されたら残りは消費せず即座に打ち切る
  // （拒否後も残りコストを消費し続けると、拒否の原因になった超過分をさらに広げてしまう）。
  for (let i = 0; i < cost; i += 1) {
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
}
