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
 * 判定できない事情（接続元不明・binding 未提供・salt 未設定）があれば **フェイルオープン**（黙って通す）。
 * これは「握り潰し」ではなく、設定不備や実行環境の違いでサービス全体を止めないための意図的な設計判断。
 *
 * 🔴 **判定順は「IP → binding → salt」**（Issue #442 のセルフレビュー指摘）。salt を先に見て
 * 早期 return すると、**Workers 上で salt だけが欠けた状態**（`wrangler secret` の付け替え・
 * Workers Builds 移行〈`D-31`〉・別環境への再デプロイで引き継がれなかった場合）が
 * 「binding 未提供のローカル実行」と区別できず、`search:` と `gems:` の両方が同時に、
 * 例外も警告も無く無効化される。binding を先に取ることで「Workers 上で動いているのに salt が無い」
 * という異常だけを切り分けて警告できる（下記 3.）。
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

  // 2. binding 未提供環境（ローカル `npm test` / `next dev` / Cloudflare 実行環境の外）では
  //    そもそも Cloudflare Rate Limiting を呼びようがないため間引かない
  //    （`WorkersRateLimit` 自体も binding undefined でフェイルオープンするが、
  //    ここで早期 return してハッシュ化コストも避ける）。
  //    🔵 ここが「実行環境の判定」を兼ねるため salt より先に置く。取得コストは
  //    動的 import（モジュールキャッシュ後はほぼ無コスト）+ env 参照のみで、
  //    salt チェックを先に置いて節約できる分より、区別できない無音の全面無効化を
  //    無くす価値のほうが大きい。
  const binding = await rateLimiterBinding()
  if (!binding) {
    return
  }

  // 3. salt が未設定 / 空なら鍵を作れない。ここで生 IP をキーにすると
  //    cloudflare-infrastructure.md §9.1 の HMAC 化要件に反し、かといって salt なしで
  //    固定文字列をキーにすると全利用者が 1 つのキーを共有して過剰に制限し合う。
  //    どちらも避けるため、この環境（salt 未設定）では間引かない。
  //    🔴 ただし **binding があるのに salt が無い = Workers 上での設定不備** なので、
  //    ここだけは黙って通さず警告を残す（無音のまま全経路が無効化され、CPU 課金が
  //    跳ねるまで誰も気づかない状態を防ぐ）。binding 未提供のローカル実行は 2. で
  //    既に return しているため、テスト出力やローカル開発は従来どおり完全に無音のまま。
  const salt = process.env.RATE_LIMIT_SALT
  if (!salt) {
    // 秘密情報（salt 本体・キー・IP）は載せない。設定不備の事実だけを伝える。
    warn('RATE_LIMIT_SALT 未設定のため間引きを無効化しています')
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

/**
 * 警告ログ。`[AssetReader]` / `[StaticGemIndex]` と同じく、モジュール名の接頭辞を付けた
 * `console.warn` に寄せる（本プロジェクトの既存の流儀）。
 *
 * 🔵 発生ごとに出す（1 プロセス 1 回に間引かない）。設定不備が続いている間は
 * 出続けたほうが検知しやすく、そもそも正常な環境では 1 度も出ない。
 */
function warn(message: string): void {
  console.warn(`[rate-limit] ${message}`)
}
