import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * 横スクロール退行ガード（`NFR-15` / WCAG 2.2 SC 1.4.10 Reflow）。
 *
 * 背景: 本番の検索結果で、GitHub の `description` に含まれる長い URL が折り返されず
 * ページ全体に横スクロールが発生した。`e2e/sp-10.spec.ts` にも同じ述語
 * （`document.scrollingElement` の `scrollWidth <= clientWidth`）はあったが、
 * **既定スタブの文字列がどれも短く改行機会を含んでいた**ため検知できなかった。
 * ここでは「改行機会がゼロの連続長文字列」を含む専用データセット
 * （`e2e/stub/server.mjs` のマーカー `overflow-guard`）を 320px 幅で描画して検証する。
 *
 * 議論記録: `content/discussions/horizontal_overflow_20260823/whiteboard.md`
 *
 * 🔴 viewport は **320px 単独**。320 CSS px は SC 1.4.10 の達成基準文言に名指しされた唯一の
 * 閾値であり、改行不能文字列に必要な幅は viewport 幅に依存せず一定なので、
 * 320 を通れば 375 / 430 は論理的に導ける（固定幅ブレークポイントを使わない
 * `ui-ux-guidelines.md` §3 の制約が前提）。
 *
 * 🔴 `body` / `html` に `overflow-x: hidden` / `clip` を足してはならない。`body` が
 * `overflow` を明示した時点で viewport への伝播が止まり、**この述語が恒久的に green** になる
 * （溢れが復活しても検知できなくなる）。
 */

/** 横スクロールが発生していないこと（`clientWidth` は縦スクロールバー分を除いた値）。 */
async function expectNoHorizontalScroll(page: Page, label: string): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }
  })
  // +1px は sub-pixel 丸め対策
  expect(overflow.scrollWidth, `${label}: ${JSON.stringify(overflow)}`).toBeLessThanOrEqual(
    overflow.clientWidth + 1,
  )
}

/** マーカーは部分一致なので接尾辞を足してよい（試行ごとのキャッシュ衝突を避ける）。 */
function uniqueOverflowGuardKeyword(): string {
  return `overflow-guard-${randomBytes(4).toString('hex')}`
}

test.describe('横スクロール退行ガード（NFR-15 / SC 1.4.10）', () => {
  test.use({ viewport: { width: 320, height: 720 } })

  test('320px 幅で、折り返せない長文字列を含む検索結果を出しても横スクロールが発生しない', async ({
    page,
  }) => {
    await page.goto('/ja')
    await expectNoHorizontalScroll(page, '検索前のトップ')

    await searchFor(page, uniqueOverflowGuardKeyword())

    // 3 件（長い URL 入り description / 長い単一 topic / 長いリポジトリ名）がすべて描画されるのを待つ。
    await expect(page.getByRole('link', { name: 'octostub/overflow-guard-description' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'octostub/overflow-guard-topic' })).toBeVisible()
    await expect(
      page.getByRole('link', { name: `octostub/overflow-guard-${'n'.repeat(48)}` }),
    ).toBeVisible()

    await expectNoHorizontalScroll(page, '検索結果一覧')
  })

  test('320px 幅で、折り返せない長文字列を含む詳細ページを開いても横スクロールが発生しない', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueOverflowGuardKeyword())

    await page.getByRole('link', { name: 'octostub/overflow-guard-description' }).click()
    await expect(
      page.getByRole('heading', { name: /octostub\/overflow-guard-description/ }),
    ).toBeVisible()

    await expectNoHorizontalScroll(page, '詳細ページ（長い URL 入り description）')
  })
})
