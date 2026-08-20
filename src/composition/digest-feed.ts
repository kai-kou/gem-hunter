import type { DateSeed } from '../domain/model/date-seed'
import type { DailyDigest, DigestMeta } from '../domain/model/gem'
import { renderDigestRss } from '../infrastructure/feed/digest-rss'
import { getDailyDigestUseCase } from './container'

/**
 * RSS 配信（`US-33`）の composition。`app`（route handler）は infrastructure を直接
 * import できない（ARCH-3）ため、usecase 取得と RSS シリアライズ（infrastructure）の
 * 束ねをここで行い、route からは本関数だけを呼ぶ。
 */

/**
 * 候補プール読み込みが将来の実装差し替えで例外を投げても配信を止めないための空メタ
 * （現行 `StaticGemDigest` は例外を投げず空配列へフォールバックする・`D-28` SPOF 方針）。
 */
const EMPTY_META: DigestMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '',
}

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
    digest = { date: opts.seed, items: [], meta: EMPTY_META }
  }
  return renderDigestRss(digest, { origin: opts.origin })
}
