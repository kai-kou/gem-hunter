import { RateLimitExceededError } from '../domain/errors'
import { rateLimiterBinding } from '../infrastructure/platform/cloudflare-bindings'
import { clientIpOf, hashRateLimitKey } from '../infrastructure/platform/rate-limit-key'
import { RATE_LIMIT_PERIOD_SECONDS, WorkersRateLimit } from '../infrastructure/platform/rate-limit'

/**
 * composition root（Issue #122 / #442）。検索経路（画面 / GET /api/search）と Gem 一覧
 * （`/{locale}/gems`）の自リクエスト間引きを `RateLimitPort`（`WorkersRateLimit`）へ
 * 実際に配線する唯一の場所。
 * 検索・詳細取得の組み立て（`container.ts`）や認証（`auth.ts`）と同じく、composition root を
 * 関心ごとにファイルへ分けている（`src/composition/` 配下全体が composition root・architecture §2.1）。
 */

/**
 * 経路をまたいで共通の間引き処理。呼び出し側は Cloudflare Rate Limiting のキー接頭辞だけを渡す。
 *
 * 判定できない事情（接続元不明・salt 未設定・binding 未提供）があれば **フェイルオープン**（黙って通す）。
 * これは「握り潰し」ではなく、設定不備や実行環境の違いでサービス全体を止めないための意図的な設計判断。
 *
 * @param keyPrefix Cloudflare Rate Limiting のキー接頭辞（`search:` / `gems:`）。
 *   接頭辞が違えばカウンタも別枠になるため、経路ごとに独立した枠を割り当てる手段になる。
 */
async function enforceRateLimit(headers: Headers, keyPrefix: string): Promise<void> {
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

  const key = `${keyPrefix}${await hashRateLimitKey(ip, salt)}`
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

/**
 * 検索経路の自リクエスト間引き（Issue #122 / NFR-7）。超過時は
 * `RateLimitExceededError('rateLimitSecondary')` を投げる。
 *
 * 守っているコストは **上流 GitHub API の枠**。フェイルオープン条件は `enforceRateLimit` を参照。
 */
export async function enforceSearchRateLimit(headers: Headers): Promise<void> {
  await enforceRateLimit(headers, 'search:')
}

/**
 * Gem 一覧（`/{locale}/gems`）の自リクエスト間引き（Issue #442）。超過時は検索経路と同じく
 * `RateLimitExceededError('rateLimitSecondary')` を投げる。
 *
 * **なぜ Gem 一覧にも掛けるのか**: `limits.cpu_ms` は 1 リクエストあたりの CPU 時間の天井であって
 * リクエスト本数を制限しない。`SP-19` で追加された Gem 一覧には本数を絞る仕組みが 1 つも無く、
 * さらに GitHub API を叩かないため上流の 403/429 に間接的に守られることもない
 * （＝ 自 Worker の CPU がそのまま費用として露出する）。
 *
 * **なぜ検索と枠を分けるのか**: 守りたいコストの種類が違う（検索 = 上流 GitHub API 枠 /
 * Gem 一覧 = 自 Worker の CPU）。枠を共有すると「検索 → Gem 一覧」という主要導線で
 * 正常な利用者どうしが枠を食い合うため、キー接頭辞を `gems:` に分けて独立した枠にする
 * （ユーザー裁定・Issue #442）。
 */
export async function enforceGemListRateLimit(headers: Headers): Promise<void> {
  await enforceRateLimit(headers, 'gems:')
}
