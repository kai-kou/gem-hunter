import { renderDailyDigestRss } from '@/src/composition/digest-feed'
import { toYyyymmdd } from '@/src/domain/model/date-seed'

/**
 * `US-33`: 日次ダイジェストの RSS 2.0 配信（`GET /api/digest/rss`）。
 *
 * 🔴 **トップページと同じ内容**にする（操作レビュー条件）ため、`limit` はトップ
 * （`app/[locale]/page.tsx` の `DAILY_DIGEST_LIMIT`）と同一の値に固定する。値を変えると
 * 「同じ内容が取得できる」が壊れるので、変更する場合は両方同時に見直すこと。
 *
 * usecase 取得と RSS シリアライズ（infrastructure）の束ねは composition
 * （`renderDailyDigestRss`）に寄せる。route は薄く保ち infrastructure を直接 import しない
 * （ARCH-3・依存規則）。
 */
const DAILY_DIGEST_LIMIT = 5

/** 現在日に依存する（`?date=` を受け付けず常に当日 UTC）ため、静的最適化の対象にしない。 */
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const origin = new URL(request.url).origin
  const seed = toYyyymmdd(new Date())
  const xml = await renderDailyDigestRss({ seed, limit: DAILY_DIGEST_LIMIT, origin })

  return new Response(xml, {
    status: 200,
    headers: {
      'content-type': 'application/rss+xml; charset=utf-8',
      'cache-control': 'public, max-age=300',
    },
  })
}
