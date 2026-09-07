import type { ClockPort } from '../domain/ports/clock-port'
import { SystemClock } from '../infrastructure/system-clock'

/**
 * 「レート制限がフェイルオープンで無効になっている」ことを運用中に検知できるようにする
 * 診断ログ（Issue #192）。
 *
 * **なぜ要るか**: `src/composition/rate-limit.ts` の間引きは、判定材料が揃わない 3 条件
 * （接続元 IP 不明 / binding 未提供 / `RATE_LIMIT_SALT` 未設定）で **黙って素通り** する。
 * これはサービス全体を止めないための意図的な設計判断だが、**「実は効いていない」状態が
 * 無音になる** という副作用を持つ。実際 PR #184 のプレビューはこの状態で、200 応答も
 * E2E 緑もそのままだったため、実機に 90 リクエスト投げるまで誰も気づかなかった（#187）。
 *
 * **なぜ間引くか**: 無効な環境ではフェイルオープンが **全リクエスト** で起きるため、
 * 素直に出すとログ量がリクエスト数に比例して溢れる（Issue #192 完了条件 2）。
 * 理由ごとに、同じ isolate 内では `RATE_LIMIT_WARN_INTERVAL_MS` に 1 回までへ抑える。
 *
 * **なぜ「isolate 起動後 1 回だけ」ではなく時間ベースか**: 1 回だけにすると、暖まった
 * isolate では二度と出ないため「無効なのに無音」と「有効だから無音」を外から区別できず、
 * 検証手段（`wrangler tail` でマーカーを待つ・`cloudflare-infrastructure.md` §3.3
 * 「無効化を外から確認する」）が成立しない。間隔を置いて再出力すれば、観測窓を
 * 間隔以上取るだけで判定でき、かつログ量はリクエスト数に比例しない。
 *
 * 🔵 **レスポンスヘッダで常時公開する案は採らない**: 内部構成（binding の有無・secret の設定状態）を
 * 誰にでも推測させることになる。`prd.md` §7 が認証・権限の失敗を「内部情報を出さず汎用エラー」
 * として扱うのと同じ方針で、内部状態は **運用者だけが読めるログ**（Workers Logs）に置く。
 *
 * ⚠️ **間引きポリシーはこのモジュールのものだけではない**: 同じ composition 層の
 * `container.ts`（`warnedCacheFallback`）は `[cache]` の warn を **isolate 生存中 1 回きり** に
 * 抑えており、時間ベースではない。`cloudflare-infrastructure.md` §3.3 の観測窓ルール
 * （間隔以上待てば必ず再出力される）は `[cache]` には適用されない。統合は別 Issue で扱う。
 */

/** フェイルオープンで間引きが行われなかった理由（`rate-limit.ts` の判定順と同じ並び）。 */
export type RateLimitDisabledReason = 'no-client-ip' | 'no-binding' | 'no-salt'

/**
 * 検証手段が grep する固定マーカー（変更すると `wrangler tail` の手順が壊れる）。
 * 手順の正本は `docs/03_design/infrastructure/cloudflare-infrastructure.md` §3.3。
 */
export const RATE_LIMIT_DISABLED_MARKER = '[rate-limit] disabled'

/** 同一理由を再出力するまでの最短間隔（ミリ秒）。検証時の観測窓の下限でもある。 */
export const RATE_LIMIT_WARN_INTERVAL_MS = 10 * 60 * 1000

/** 理由コードに添える説明。**秘密情報（salt 値・接続元 IP）は載せない**。 */
const REASON_DESCRIPTIONS: Record<RateLimitDisabledReason, string> = {
  'no-client-ip': '接続元 IP を識別できないため間引きを無効化しています',
  'no-binding': 'Rate Limiting binding（RATE_LIMITER）が未提供のため間引きを無効化しています',
  'no-salt': 'RATE_LIMIT_SALT 未設定のため間引きを無効化しています',
}

/**
 * 間引き付きの診断レポーターを作る。
 *
 * @param clock 時刻取得（テスト決定性のため `ClockPort` 経由・`architecture-rules.md` §1.5）。
 *   既定は実時刻（`SystemClock`）。
 * @returns 理由コードを受け取り、必要なら `console.warn` を 1 行出す関数。
 *   throw しない（診断が本来の処理を壊さない）。
 */
export function createRateLimitDisabledReporter(
  clock: ClockPort = new SystemClock(),
): (reason: RateLimitDisabledReason) => void {
  const lastWarnedAt = new Map<RateLimitDisabledReason, number>()

  return (reason: RateLimitDisabledReason): void => {
    const now = clock.now().getTime()
    const last = lastWarnedAt.get(reason)
    if (last !== undefined && now - last < RATE_LIMIT_WARN_INTERVAL_MS) {
      return
    }
    lastWarnedAt.set(reason, now)
    console.warn(`${RATE_LIMIT_DISABLED_MARKER} reason=${reason} — ${REASON_DESCRIPTIONS[reason]}`)
  }
}

/** アプリが使う既定のレポーター（isolate ごとに 1 つ = 間引き状態も isolate ごと）。 */
export const reportRateLimitDisabled = createRateLimitDisabledReporter()
