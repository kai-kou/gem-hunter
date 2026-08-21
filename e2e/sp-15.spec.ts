import { expect, test } from '@playwright/test'

import { readDigestPackageNames } from './helpers'

/**
 * SP-15: ダイジェストの鮮度と出典が保証され、再訪時に前回からの差分がわかる
 * （`user-story-map.md` §5.3 `SP-15` の操作レビュー手順 3 手順を E2E に写す・
 * `sprint-development-rules.md` `SD-2`）。対応 `AC`: なし（上乗せ要件 `AR-9`）。
 * 🔴 RSS 配信（旧手順 4）は `D-34`（2026-08-21）により撤去済み（`open-questions.md` 参照）。
 *
 * データ源: `public/data/daily-digest.json`。`?date=YYYYMMDD` で顔ぶれを再現できる。
 */

test.describe('SP-15: 鮮度・出典・差分', () => {
  test('手順1: 出典表示（Ecosyste.ms / CC BY-SA 4.0）とデータ生成日（JST）が出ている', async ({
    page,
  }) => {
    await page.goto('/ja')
    // 出典テキスト（`AttributionNotice`）が可視。D-33（#308）で「このデータについて: …」へ刷新済み。
    await expect(page.getByText(/このデータについて/)).toBeVisible()
    await expect(page.getByText(/Ecosyste\.ms/)).toBeVisible()
    const licenseLink = page.getByRole('link', { name: 'CC BY-SA 4.0' })
    await expect(licenseLink).toBeVisible()
    await expect(licenseLink).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
    // 生成日は JST 表示（`docs/rules/datetime-rules.md` §0）。<time> の可視テキストに ` JST` が付く。
    // `daily-digest.json` の `meta.generatedAt` は ISO 8601 UTC。
    const jstTime = page.locator('time').filter({ hasText: /JST$/ }).first()
    await expect(jstTime).toBeVisible()
    // dateTime 属性は機械可読の ISO 8601 UTC を保持する（生値のまま）。
    const dt = await jstTime.getAttribute('datetime')
    expect(dt).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/)
  })

  test('手順2: 再訪すると前回以降に入れ替わった項目が識別できる（新着バッジ）', async ({
    page,
  }) => {
    // まず 8/20 を初回訪問 → localStorage に seen 集合を書き込む
    await page.goto('/ja?date=20260820')
    const firstNames = await readDigestPackageNames(page)
    expect(firstNames.length).toBe(5)
    // 初回訪問の注記が出ている（isFirstVisit=true・個別バッジは付かない）
    const firstNote = page.getByText('初回として全件を表示しています')
    await expect(firstNote).toBeVisible()
    // 新着バッジは初回では 0 個
    const section = page.getByRole('region', { name: '今日の Gem' })
    await expect(section.getByText('新着')).toHaveCount(0)

    // effect 完了後（seen を書き込んだ後）に別の日付へ移動。write は effect で実行済み。
    // Provider は client なので effect が終わってからページ遷移する必要がある。
    // 上で firstNote が可視になっている時点で ready 状態＝ write 済み。
    await page.goto('/ja?date=20260821')
    const secondNames = await readDigestPackageNames(page)
    // 手順1の集合と比べて新規に登場した名前が >=1 あることを、以下 UI 面で検証する
    const newBadges = section.getByText('新着')
    await expect(newBadges.first()).toBeVisible()
    const badgeCount = await newBadges.count()
    expect(badgeCount).toBeGreaterThanOrEqual(1)
    // 初回注記は今回は出ない（seen が空でないため）
    await expect(page.getByText('初回として全件を表示しています')).toHaveCount(0)
    // secondNames に「新着」でないもの＝ firstNames と重複するものは、UI 側でバッジが付かない
    // （細かな 1:1 対応はコンポーネント単体テストで担保済み。ここでは >=1 個新着が出ることを見る）
    expect(secondNames.length).toBe(5)
  })

  test('手順3: ブラウザのストレージを消してから開くと「初回として全件を表示」注記が出て壊れない', async ({
    page,
    context,
  }) => {
    // 一度 seen を書く
    await page.goto('/ja?date=20260820')
    await expect(page.getByText('初回として全件を表示しています')).toBeVisible()

    // ストレージ全削除（Safari ITP の 7 日削除に相当）
    await context.clearCookies()
    await page.evaluate(() => {
      try {
        window.localStorage.clear()
      } catch {
        // Storage が使えない環境でも壊れないこと自体が本手順の要件
      }
    })

    // 再訪。エラー画面 / 空画面ではなく、初回注記付きでダイジェストが全件並ぶ。
    await page.goto('/ja?date=20260821')
    const section = page.getByRole('region', { name: '今日の Gem' })
    await expect(section).toBeVisible()
    const items = section.locator('ol > li')
    await expect(items).toHaveCount(5)
    await expect(page.getByText('初回として全件を表示しています')).toBeVisible()
    // 新着バッジは初回扱いなので 0 個
    await expect(section.getByText('新着')).toHaveCount(0)
  })
})
