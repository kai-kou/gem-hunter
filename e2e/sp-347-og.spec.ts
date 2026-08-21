import { expect, test } from '@playwright/test'

/**
 * Issue #347 セルフレビュー指摘1（CRITICAL）対応: `app/[locale]/opengraph-image.tsx` は
 * 新規追加なのに `npm test` / `npm run test:e2e` のどちらもこのルートに到達していなかった。
 * 背景データ URI の破損・`messages` の型変更・satori 非対応の CSS プロパティ混入などで
 * 実行時に例外を投げるようになっても、テストが全部緑のまま通ってしまう欠陥があった。
 *
 * 実際に本 PR で 2 回踏んだ不具合（Workers 上で 500・`og:image` が localhost を指す）を
 * 退行として検知できるようにする:
 *   1. `/{locale}/opengraph-image` への直接リクエストが 200 + `image/png` で返る
 *      （satori のレンダリング例外・背景データ URI の破損を検知）
 *   2. `/{locale}` の HTML に `og:image` メタタグが出ていて、`content` が絶対 URL
 *      （`https://` 始まり）であること（`metadataBase` 未設定 = localhost フォールバックの
 *      退行を検知・`src/composition/site-url.ts` のコメントが自認する過去の実障害）
 */
test.describe('Issue #347: OG 画像ルートの疎通確認', () => {
  test('ja: /ja/opengraph-image が 200 + image/png で返る', async ({ page }) => {
    const res = await page.request.get('/ja/opengraph-image')
    expect(res.status()).toBe(200)
    expect(res.headers()['content-type']).toBe('image/png')
    // 空応答（0 バイト）でも content-type だけは通ってしまうため、実体があることも確認する。
    const body = await res.body()
    expect(body.byteLength).toBeGreaterThan(0)
  })

  test('en: /en/opengraph-image が 200 + image/png で返る', async ({ page }) => {
    const res = await page.request.get('/en/opengraph-image')
    expect(res.status()).toBe(200)
    expect(res.headers()['content-type']).toBe('image/png')
    const body = await res.body()
    expect(body.byteLength).toBeGreaterThan(0)
  })

  test('ja: /ja の HTML に og:image メタタグがあり、content が絶対 URL（https://）である', async ({
    page,
  }) => {
    await page.goto('/ja')

    const ogImage = page.locator('meta[property="og:image"]')
    await expect(ogImage).toHaveCount(1)
    const content = await ogImage.getAttribute('content')
    expect(content).not.toBeNull()
    // 🔴 `metadataBase` 未設定だと `http://localhost:3000/...` へフォールバックする
    // （実デプロイで踏んだ退行・`src/composition/site-url.ts` コメント参照）。
    expect(content).toMatch(/^https:\/\//)
    expect(content).not.toContain('localhost')
  })

  test('en: /en の HTML に og:image メタタグがあり、content が絶対 URL（https://）である', async ({
    page,
  }) => {
    await page.goto('/en')

    const ogImage = page.locator('meta[property="og:image"]')
    await expect(ogImage).toHaveCount(1)
    const content = await ogImage.getAttribute('content')
    expect(content).not.toBeNull()
    expect(content).toMatch(/^https:\/\//)
    expect(content).not.toContain('localhost')
  })
})
