import { randomInt } from 'node:crypto'

import { expect, test } from '@playwright/test'

/**
 * Workers ランタイム依存のレート制限を検証する E2E（Issue #188）。
 *
 * `playwright.config.ts`（既定）は `next start` で起動するため `RATE_LIMITER` binding が
 * 常に `undefined` になり、この振る舞いを一度も踏めない（`src/composition/rate-limit.ts` の
 * フェイルオープン条件 2.）。本ファイルは `playwright.workers.config.ts`（`wrangler dev` を
 * webServer に使う）でのみ実行する:
 *
 *   npm run test:e2e:workers
 *
 * `wrangler.jsonc` の `ratelimits[].simple` は `limit: 60, period: 60`（60 req/60s）。
 */

const RATE_LIMIT = 60

/** テスト間でレート制限バケットが衝突しないよう、呼び出しごとに一意な接続元 IP を作る。 */
function uniqueIp(): string {
  // TEST-NET-3（RFC 5737・203.0.113.0/24）を使う（実在ネットワークと衝突しない予約範囲）。
  return `203.0.113.${randomInt(1, 255)}`
}

test.describe('レート制限（Workers ランタイム）', () => {
  test('レート制限超過で /api/search が 429 + Retry-After を返す', async ({ request }) => {
    const ip = uniqueIp()
    const total = RATE_LIMIT + 10

    const responses = await Promise.all(
      Array.from({ length: total }, (_, i) =>
        request.get(`/api/search?q=throttle-probe-${i}`, {
          headers: { 'cf-connecting-ip': ip },
        }),
      ),
    )

    const statuses = responses.map((r) => r.status())
    const okCount = statuses.filter((s) => s === 200).length
    const limitedCount = statuses.filter((s) => s === 429).length

    // 固定窓（60 req/60s）なので、超過分の一部が 429 になる。並行実行の到達順序までは
    // 固定できないため「ちょうど 60/10」ではなく上限・下限の帯で確認する。
    expect(okCount).toBeLessThanOrEqual(RATE_LIMIT)
    expect(limitedCount).toBeGreaterThan(0)
    expect(okCount + limitedCount).toBe(total)

    const limited = responses.find((r) => r.status() === 429)
    expect(limited).toBeDefined()
    expect(limited?.headers()['retry-after']).toBe('60')
    const body = await limited?.json()
    expect(body?.kind).toBe('rateLimitSecondary')
    expect(body?.retryAfterSeconds).toBe(60)
  })

  test('画面がレート制限超過時に再試行案内を表示する', async ({ page, request }) => {
    const ip = uniqueIp()

    // 枠を使い切るまでは API へ流し込み（同じ search: バケットを共有する・
    // `src/composition/rate-limit.ts` のキー接頭辞）、最後の 1 回だけブラウザで画面を開く。
    // 🔴 ちょうど RATE_LIMIT 件ではなく余裕を持たせる（1本目のテストと同じ考え方・Layer 1 指摘）:
    // 固定窓の境界とフラッドの実行タイミングが完全に一致する保証はなく、ちょうど RATE_LIMIT 件だと
    // 窓のロールオーバー次第で枠を使い切れず画面側が 429 にならない flaky リスクがある。
    await Promise.all(
      Array.from({ length: RATE_LIMIT + 10 }, (_, i) =>
        request.get(`/api/search?q=throttle-screen-probe-${i}`, {
          headers: { 'cf-connecting-ip': ip },
        }),
      ),
    )

    await page.setExtraHTTPHeaders({ 'cf-connecting-ip': ip })
    await page.goto('/ja?q=throttle-screen-probe-final')

    // `role="alert"` は Next.js のルート遷移アナウンサー（`__next-route-announcer__`）とも一致する
    // ため、文言でスコープを絞る（`src/ui/error-notice.tsx` の `role="alert"` が対象）。
    const alert = page.getByRole('alert').filter({ hasText: '秒後に再度お試しください' })
    await expect(alert).toBeVisible()
  })
})
