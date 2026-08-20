import type { DateSeed } from '../domain/model/date-seed'
import type { DailyDigest } from '../domain/model/gem'
import { renderDigestRss } from '../infrastructure/feed/digest-rss'
import { FALLBACK_META } from '../infrastructure/platform/static-gem-digest'
import { getDailyDigestUseCase } from './container'

/**
 * RSS 配信（`US-33`）の composition。`app`（route handler）は infrastructure を直接
 * import できない（ARCH-3）ため、usecase 取得と RSS シリアライズ（infrastructure）の
 * 束ねをここで行い、route からは本関数だけを呼ぶ。
 */

/**
 * ダイジェストの表示件数（`ADR 0014` §2.1 の既定 5 件）。
 * 🔴 **トップページ（`app/[locale]/page.tsx`）と RSS（`app/api/digest/rss/route.ts`）で
 * 同じ値を使う**（操作レビュー条件「RSS を購読するとトップと同じ内容が取得できる」）。
 * 定数を各所へ複製すると片方だけ変えても機械検査が通り、要件が静かに壊れる
 * （Layer 1 セルフレビュー指摘）。
 */
export const DAILY_DIGEST_LIMIT = 5

/**
 * 現在日シードの日次ダイジェストを取得し、RSS 2.0 文字列へシリアライズする。
 * `limit` はトップページ（`app/[locale]/page.tsx` の `DAILY_DIGEST_LIMIT`）と同一値を
 * 渡すことで「トップと同じ内容」（操作レビュー条件）を満たす。
 */
export async function renderDailyDigestRss(opts: {
  seed: DateSeed
  limit: number
  origin: string
}): Promise<string> {
  let digest: DailyDigest
  try {
    digest = await getDailyDigestUseCase()({ seed: opts.seed, limit: opts.limit })
  } catch {
    digest = { date: opts.seed, items: [], meta: FALLBACK_META }
  }
  return renderDigestRss(digest, { origin: opts.origin })
}
