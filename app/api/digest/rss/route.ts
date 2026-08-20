import { resolveLandingHost } from '@/src/composition/auth'
import { DAILY_DIGEST_LIMIT, renderDailyDigestRss } from '@/src/composition/digest-feed'
import { toYyyymmdd } from '@/src/domain/model/date-seed'

/**
 * `US-33`: 日次ダイジェストの RSS 2.0 配信（`GET /api/digest/rss`）。
 *
 * 🔴 **トップページと同じ内容**にする（操作レビュー条件）ため、`limit` はトップ
 * とも共有する `DAILY_DIGEST_LIMIT`（`src/composition/digest-feed.ts`）を使う。
 * 定数を複製せず 1 箇所から import することで「同じ内容が取得できる」を構造的に保証する。
 *
 * usecase 取得と RSS シリアライズ（infrastructure）の束ねは composition
 * （`renderDailyDigestRss`）に寄せる。route は薄く保ち infrastructure を直接 import しない
 * （ARCH-3・依存規則）。
 */

/** 現在日に依存する（`?date=` を受け付けず常に当日 UTC）ため、静的最適化の対象にしない。 */
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  // 🔴 クライアント送信の `Host` を無検証で使わない（`app/api/auth/callback/route.ts` の
  //    `landingUrl()` と同じ理由・PR #141 レビュー指摘）。RSS は `cache-control: public` で
  //    共有キャッシュに載るため、偽装 Host がそのまま `<link>` / `<guid>` に焼き付くと
  //    購読者全員が攻撃者ドメインへ誘導される（Host header cache poisoning）。
  //    `resolveLandingHost()` は許可ホスト（`GITHUB_OAUTH_CALLBACK_URL` 由来）と一致する場合のみ
  //    リクエストホストを使い、一致しなければ許可ホストへフォールバックする。
  const requestUrl = new URL(request.url)
  const origin = `${requestUrl.protocol}//${resolveLandingHost(requestUrl.host)}`
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
