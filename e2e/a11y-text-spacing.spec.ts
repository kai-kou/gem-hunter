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

/**
 * SC 1.4.12 の 4 値をすべて強制する CSS をページに注入する。
 *
 * 🔴 注入後に `document.fonts.ready` と、CSS トランジションの収束を待つ（Issue #831 の真因）。
 *
 * 実測で判明した非決定性の正体: `src/ui/components/button.tsx` の `buttonVariants` 基底クラスに
 * `transition-all` が含まれており、これは `letter-spacing` / `line-height` / `word-spacing` も
 * トランジション対象にする。本関数が注入する CSS はこれらのプロパティを `normal` から
 * 一気に強制値へ変えるため、**ボタン系要素では即座に最終値へならず、既定 150ms のトランジション
 * 中は値が補間される**。測定タイミングがこのトランジション途中に重なると、同一要素・同一条件でも
 * 実測 `letter-spacing` が毎回異なり（実測: 0.72px 〜 1.68px の間でばらつき）、それに伴って
 * `scrollWidth` の超過量も 2px 〜 8.7px の間で揺れる（フルスイート実行時の CPU 競合で
 * このタイミングがずれやすいため「フルスイート実行時のみ非決定的に失敗」して見えていた）。
 * トランジションが収束した後の実効値（14px 要素なら 0.12 × 14 = 1.68px）で測れば決定的になる。
 */
async function injectTextSpacingOverride(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
* {
  line-height: 1.5 !important;
  letter-spacing: 0.12em !important;
  word-spacing: 0.16em !important;
  /*
   * 🔴 Issue #831 の真因対策: \`src/ui/components/button.tsx\` の \`buttonVariants\` 基底クラスに
   * 含まれる \`transition-all\` は letter-spacing / line-height / word-spacing もトランジション
   * 対象にする。上記 3 値を \`normal\` から一気に強制値へ変えると、ボタン系要素だけ既定 150ms の
   * トランジション中は値が補間され、測定タイミング次第で実効 letter-spacing が
   * 0.72px 〜 1.68px の間でばらついた（scrollWidth の超過量も 2px 〜 8.7px の間で揺れ、
   * フルスイート実行時の CPU 競合でタイミングがずれやすいぶん「フルスイート実行時のみ
   * 非決定的に失敗」して見えていた）。本検査は達成基準の 4 値が **実効値として即座に**
   * 効いているかを見るためのものであり、そのトランジション自体を検証対象にしていないため、
   * ここで無効化して即時適用させる。
   */
  transition: none !important;
}
p {
  margin-bottom: 2em !important;
}
`,
  })
  // Web フォント（Geist）のスワップ（FOUT/FOIT）が完了する前に測ると、フォールバック
  // フォントとスワップ後のフォントとで文字幅が異なり実測値が揺れるため、フォント読み込み
  // 完了も待つ（上記トランジション無効化と合わせて、実効値の測定を完全に決定的にする）。
  await page.evaluate(() => document.fonts.ready)
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

/**
 * `container` 配下で要素がクリップされて中身が失われていないことを確認する。
 * `toBeVisible()` は祖先の `overflow: hidden` 等によるクリップを検出しないため、
 * `scrollHeight`（実コンテンツの高さ）が `clientHeight`（見えている高さ）を超えていないかを
 * 直接測る（+1 は端数丸め用の許容）。
 */
async function expectNoClipping(container: Locator, label: string): Promise<void> {
  const overflowing = await container.evaluate((el) => el.scrollHeight > el.clientHeight + 1)
  expect(
    overflowing,
    `${label}: コンテンツがクリップされている（scrollHeight がクリップ許容値を超えて clientHeight を上回る）`,
  ).toBe(false)
}

/**
 * 注入した Text Spacing 上書き（`line-height` / `letter-spacing` / `word-spacing`）が
 * `container` 配下の代表要素に実際に効いているかを `getComputedStyle` で直接確認する。
 * 宣言（CSS を注入したこと）だけでなく、実効値（computed value）で判定する。
 */
async function expectTextSpacingAppliedWithin(container: Locator, label: string): Promise<void> {
  const target = container.locator('p, td').first()
  await expect(target, `${label}: 代表要素（p / td）が見つからない`).toBeVisible()

  const metrics = await target.evaluate((el) => {
    const style = getComputedStyle(el)
    return {
      fontSize: Number.parseFloat(style.fontSize),
      lineHeight: Number.parseFloat(style.lineHeight),
      letterSpacing: Number.parseFloat(style.letterSpacing),
      wordSpacing: Number.parseFloat(style.wordSpacing),
    }
  })

  // 浮動小数の丸め誤差を吸収するため、絶対値側に -0.01px の許容を入れる（比率でなく px 同士で比較）。
  expect(
    metrics.lineHeight,
    `${label}: line-height 不足（実測 ${metrics.lineHeight}px, font-size ${metrics.fontSize}px）`,
  ).toBeGreaterThanOrEqual(metrics.fontSize * 1.5 - 0.01)
  expect(
    metrics.letterSpacing,
    `${label}: letter-spacing 不足（実測 ${metrics.letterSpacing}px, font-size ${metrics.fontSize}px）`,
  ).toBeGreaterThanOrEqual(metrics.fontSize * 0.12 - 0.01)
  expect(
    metrics.wordSpacing,
    `${label}: word-spacing 不足（実測 ${metrics.wordSpacing}px, font-size ${metrics.fontSize}px）`,
  ).toBeGreaterThanOrEqual(metrics.fontSize * 0.16 - 0.01)
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
    const cards = page.locator('ul.divide-border > li')
    await expectNoVerticalOverlap(cards, '検索結果カード')

    // `toBeVisible()` は祖先の overflow クリップを検出しないため、各カードで
    // 内容がクリップされて隠れていないか（scrollHeight <= clientHeight）を直接測る。
    const cardCount = await cards.count()
    for (let i = 0; i < cardCount; i++) {
      await expectNoClipping(cards.nth(i), `検索結果カード[${i}]`)
    }

    // 上書き後も 3 件のリンクが引き続き見えている（クリップ・重なりで隠れていない）ことを確認する。
    await expect(descriptionCard).toBeVisible()
    await expect(topicCard).toBeVisible()
    await expect(longNameCard).toBeVisible()
  })

  /**
   * Issue #831 の再現専用テスト。
   *
   * フルスイート実行時にのみ、上の「検索結果一覧」テストが `scrollWidth` の 2〜6px 超過で
   * 非決定的に落ちていた。採取した `culprit`（PR 起点コメント）は、カード上部の
   * 「この検索語の Gem 候補を一覧で見る」導線（`GemListLink`）で、`whitespace-nowrap` を
   * 持つボタン風リンクが Text Spacing 上書き後の `letter-spacing` 実効値ぶん伸び、
   * 320px 幅の viewport からはみ出していた。
   *
   * `document.scrollingElement` 全体を見る `expectNoHorizontalScroll` は非決定的な再現に
   * 頼っていたため、ここでは **当該要素そのもの**の `getBoundingClientRect().right` を直接測る。
   * これにより、フルスイート実行という間接的な条件を経由せず、単体実行でも決定的に検証できる。
   */
  test('「この検索語の Gem 候補を一覧で見る」導線は Text Spacing 上書き後も画面幅からはみ出さない', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueOverflowGuardKeyword())

    const gemListLink = page.getByRole('link', { name: 'この検索語の Gem 候補を一覧で見る' })
    await expect(gemListLink).toBeVisible()

    await injectTextSpacingOverride(page)

    const box = await gemListLink.evaluate((el) => ({
      right: el.getBoundingClientRect().right,
      viewportWidth: window.innerWidth,
      letterSpacing: getComputedStyle(el).letterSpacing,
    }))
    // +1px はサブピクセル丸め対策（`expectNoHorizontalScroll` と同じ許容）。
    expect(
      box.right,
      `この検索語の Gem 候補を一覧で見る: right=${box.right} viewportWidth=${box.viewportWidth} letterSpacing=${box.letterSpacing}`,
    ).toBeLessThanOrEqual(box.viewportWidth + 1)

    await expectNoHorizontalScroll(page, '検索結果一覧（導線のみ再検証・Text Spacing 上書き後）')
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

    // `.readme-content` は `overflow-x-auto` を持ちコンテナ内部スクロールに横方向の増大を吸収する
    // ため、`expectNoHorizontalScroll`（`document.scrollingElement` 検査）だけでは
    // `.readme-content` 配下に注入した 4 値が実際に効いているかを測れない。代表要素の
    // computed style を直接測り、かつクリップで消えていないことも確認する。
    const readmeContent = page.locator('.readme-content')
    await expectTextSpacingAppliedWithin(readmeContent, 'README 本文（.readme-content）')
    await expectNoClipping(readmeContent, 'README 本文（.readme-content）')
  })
})
