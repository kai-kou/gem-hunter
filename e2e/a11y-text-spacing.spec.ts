import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { expectNoHorizontalScroll, searchFor, uniqueKeyword } from './helpers'

/**
 * WCAG 2.2 SC 1.4.12 Text Spacing の E2E 検査（Issue #53 残作業）。
 *
 * `docs/03_design/ui-ux/ui-ux-guidelines.md` は現時点で SC 1.4.12 固有の判断基準を持たない
 * （grep で無検出を確認済み）。よって本ファイルは新しい基準を新設せず、達成基準の文言が
 * 明示する 4 値をそのまま採用する:
 *   - `line-height` ≥ 1.5 × フォントサイズ
 *   - 段落後の間隔 ≥ 2 × フォントサイズ
 *   - `letter-spacing` ≥ 0.12 × フォントサイズ
 *   - `word-spacing` ≥ 0.16 × フォントサイズ
 *
 * 検査手法は `page.addStyleTag` で上記を強制する CSS を注入し、
 * ① 横スクロールが発生しない（`e2e/overflow-guard.spec.ts` / `expectNoHorizontalScroll` と同じ述語）
 * ② 主要なテキスト要素同士が重ならない（カード同士の縦位置が入れ替わらない）
 * ③ 主要なテキスト要素が上書き後も引き続き見える（クリップで消えていない）
 * の 3 点を確認する。`letter-spacing` / `word-spacing` を `em` 単位で注入するのは、`em` が
 * 適用先要素自身の `font-size` を基準に解決されるため、達成基準の「要素自身のフォントサイズの
 * 0.12/0.16 倍」という定義とそのまま一致する（px 固定値だと要素ごとのフォントサイズ差を無視してしまう）。
 *
 * フィクスチャは既存 2 種を流用する（新規データセットを増やさない）:
 *   - `overflow-guard`（`e2e/overflow-guard.spec.ts` と同じ検索結果一覧・3 件のカード）
 *   - `octostub/octo-readme-rich`（`e2e/readme-typography.spec.ts` と同じ、表・コードブロック・
 *     長い URL を含む README 詳細ページ）
 */

function uniqueOverflowGuardKeyword(): string {
  return uniqueKeyword('overflow-guard')
}

/** SC 1.4.12 の 4 値をすべて強制する CSS をページに注入する。 */
async function injectTextSpacingOverride(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
* {
  line-height: 1.5 !important;
  letter-spacing: 0.12em !important;
  word-spacing: 0.16em !important;
}
p {
  margin-bottom: 2em !important;
}
`,
  })
}

/**
 * `items` に列挙した要素（DOM 順）が縦方向に重ならないことを確認する。
 * `line-height` 拡大でカードが伸びたときに、後続カードの `top` が前カードの `bottom` より
 * 手前に来てしまう（＝テキスト同士の視覚的な重なり）ケースを検知する。
 */
async function expectNoVerticalOverlap(items: Locator, label: string): Promise<void> {
  const boxes = await items.evaluateAll((elements) =>
    elements.map((el) => {
      const rect = el.getBoundingClientRect()
      return { top: rect.top, bottom: rect.bottom }
    }),
  )
  expect(boxes.length, `${label}: 対象要素が見つからない`).toBeGreaterThan(0)
  for (let i = 1; i < boxes.length; i++) {
    expect(
      boxes[i].top,
      `${label}: 項目 ${i} が直前の項目と重なっている（top=${boxes[i].top}, prevBottom=${boxes[i - 1].bottom}）`,
    ).toBeGreaterThanOrEqual(boxes[i - 1].bottom - 1)
  }
}

test.describe('WCAG 2.2 SC 1.4.12 Text Spacing', () => {
  // 🔴 `e2e/overflow-guard.spec.ts` と同じ理由で 320px 単独（SC 1.4.10 と同じ根拠：
  // 320 CSS px は Reflow 系達成基準が名指しする最小 viewport 幅であり、ここで折り返し・
  // 溢れが起きないことを確認すれば、より広い viewport では論理的に導ける）。
  test.use({ viewport: { width: 320, height: 720 } })

  test('検索結果一覧に Text Spacing 上書きを適用しても横スクロールが発生せず、カードが重ならず見え続ける', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueOverflowGuardKeyword())

    const descriptionCard = page.getByRole('link', { name: 'octostub/overflow-guard-description' })
    const topicCard = page.getByRole('link', { name: 'octostub/overflow-guard-topic' })
    const longNameCard = page.getByRole('link', {
      name: `octostub/overflow-guard-${'n'.repeat(48)}`,
    })
    await expect(descriptionCard).toBeVisible()
    await expect(topicCard).toBeVisible()
    await expect(longNameCard).toBeVisible()

    await injectTextSpacingOverride(page)

    await expectNoHorizontalScroll(page, '検索結果一覧（Text Spacing 上書き後）')
    // カードは `<ul className="divide-border divide-y">` の直接の子（各カードの topics
    // ネスト `<ul>` は `divide-border` を持たないため誤って対象に含まれない）。
    await expectNoVerticalOverlap(page.locator('ul.divide-border > li'), '検索結果カード')

    // 上書き後も 3 件のリンクが引き続き見えている（クリップ・重なりで隠れていない）ことを確認する。
    await expect(descriptionCard).toBeVisible()
    await expect(topicCard).toBeVisible()
    await expect(longNameCard).toBeVisible()
  })

  test('README（表・コードブロックを含む長文コンテンツ）に Text Spacing 上書きを適用しても横スクロールが発生せず、見出し・本文が見え続ける', async ({
    page,
  }) => {
    await page.goto('/ja/repos/octostub/octo-readme-rich')
    await expect(page.locator('#readme-heading')).toBeVisible()
    await expect(page.locator('.readme-content table')).toBeVisible()

    await injectTextSpacingOverride(page)

    await expectNoHorizontalScroll(page, '詳細ページ（README, Text Spacing 上書き後）')
    await expect(page.locator('#readme-heading')).toBeVisible()
    await expect(page.locator('.readme-content table')).toBeVisible()
  })
})
