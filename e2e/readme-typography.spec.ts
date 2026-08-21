import { expect, test } from '@playwright/test'

/**
 * Issue #339: 詳細画面の README に書式を反映する回帰検査。
 *
 * 設計は `content/discussions/readme_typography_20260821/whiteboard.md` round3 `lead` の
 * 合意・裁定（争点 A〜F）が正本。現行の検査群（axe / Lighthouse / check_ui_dimensions.py /
 * check_contrast.py）は「書式が当たっていないこと」自体を検知できなかった（争点 F）ため、
 * 本ファイルは **クラス名の有無ではなく計算後スタイル（computed style）** を検証する。
 *
 * フィクスチャは `e2e/stub/server.mjs` の `octostub/octo-readme-rich`（README エンドポイントに
 * `readme-rich` を含むリポジトリ名を渡すと、見出し・段落・ネストした箇条書き・番号付きリスト・
 * 引用・列数が多く横に長い表・長い行を含むコードブロック・インラインコード・長い URL・
 * バッジ画像を網羅した README HTML を返す）。
 *
 * README 本文コンテナは `class="readme-content prose ..."` を持つ契約（lane_style 実装）。
 * `.readme-content` を掴んで実効スタイルを取得する（クラス名の存在確認では終わらせない）。
 */

const README_RICH_PATH = '/ja/repos/octostub/octo-readme-rich'

test.describe('Issue #339: README の書式反映（typography トークン回帰検査）', () => {
  test('README 内の h3（+2 降格後の最上位見出し）は本文（p）より大きく、ページのセクション見出し（h2）を超えない', async ({
    page,
  }) => {
    await test.step('README を含む詳細ページを開く', async () => {
      await page.goto(README_RICH_PATH)
      // 🔴 `getByRole('heading', { name: 'README' })` は部分一致のため、フィクスチャの
    //    リポジトリ名 `octo-readme-rich` 自体が「readme」を含み誤ヒットする（大文字小文字を
    //    区別しないロール名照合の既知の落とし穴）。セクション見出しは id で一意に掴む。
    await expect(page.locator('#readme-heading')).toBeVisible()
    })

    const sectionHeading = page.locator('#readme-heading')
    const readmeH3 = page.locator('.readme-content h3').first()
    const readmeP = page.locator('.readme-content p').first()

    await expect(readmeH3).toBeVisible()
    await expect(readmeP).toBeVisible()

    await test.step('計算後フォントサイズを比較する', async () => {
      const [sectionHeadingPx, h3Px, pPx] = await Promise.all([
        sectionHeading.evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
        readmeH3.evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
        readmeP.evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
      ])

      expect(h3Px, `README h3=${h3Px}px, README p=${pPx}px`).toBeGreaterThan(pPx)
      expect(
        h3Px,
        `README h3=${h3Px}px, ページのセクション見出し(h2 #readme-heading)=${sectionHeadingPx}px`,
      ).toBeLessThanOrEqual(sectionHeadingPx)
    })
  })

  test('README 本文の文字色がサイトのトークン由来である（プラグイン既定の gray スケールを使わない）', async ({
    page,
  }) => {
    await page.goto(README_RICH_PATH)

    const paragraph = page.locator('.readme-content p').first()
    await expect(paragraph).toBeVisible()

    // 🔴 `--tw-prose-*` をセマンティックトークンへ全マッピングする設計（争点 A の必須条件）が
    //    実際に効いているかを、**計算後の色** で確認する。プラグイン本体は既定の gray スケールを
    //    `@layer utilities` の中で定義しており、こちらの上書きは unlayered なので勝つはずだが、
    //    「勝っているつもり」で退行しても静的検査では気づけない（`check_prose_tokens.py` は
    //    `app/globals.css` の記述しか見ない）。ページ全体の前景色と一致することを実測で押さえる。
    const { readmeColor, pageColor } = await paragraph.evaluate((el) => ({
      readmeColor: getComputedStyle(el).color,
      pageColor: getComputedStyle(document.body).color,
    }))

    expect(readmeColor, `README 本文の色（${readmeColor}）がページ本文の色（${pageColor}）と一致`).toBe(
      pageColor,
    )
  })

  test('README 内のリストにマーカーが付き、インデントされている', async ({ page }) => {
    await page.goto(README_RICH_PATH)

    const list = page.locator('.readme-content ul').first()
    await expect(list).toBeVisible()

    const { listStyleType, paddingLeftPx } = await list.evaluate((el) => {
      const cs = getComputedStyle(el)
      return { listStyleType: cs.listStyleType, paddingLeftPx: parseFloat(cs.paddingLeft) }
    })

    expect(listStyleType, 'ul の list-style-type').not.toBe('none')
    expect(paddingLeftPx, 'ul の padding-left（インデント量）').toBeGreaterThan(0)
  })

  test('README 内のコードブロック（pre）に背景色が付く', async ({ page }) => {
    await page.goto(README_RICH_PATH)

    const pre = page.locator('.readme-content pre').first()
    await expect(pre).toBeVisible()

    const { preBackgroundColor, parentBackgroundColor } = await pre.evaluate((el) => {
      const parent = el.parentElement
      return {
        preBackgroundColor: getComputedStyle(el).backgroundColor,
        parentBackgroundColor: parent
          ? getComputedStyle(parent).backgroundColor
          : 'rgba(0, 0, 0, 0)',
      }
    })

    const isTransparent = (color: string): boolean =>
      color === 'rgba(0, 0, 0, 0)' || color === 'transparent'

    expect(isTransparent(preBackgroundColor), `pre の background-color=${preBackgroundColor}`).toBe(
      false,
    )
    expect(
      preBackgroundColor,
      `pre の背景色（${preBackgroundColor}）が親要素の背景色（${parentBackgroundColor}）と異なること`,
    ).not.toBe(parentBackgroundColor)
  })

  test('横に長い表・長いコード行・長い URL があっても body に横スクロールが出ない（デスクトップ幅）', async ({
    page,
  }) => {
    await page.goto(README_RICH_PATH)
    // 🔴 `getByRole('heading', { name: 'README' })` は部分一致のため、フィクスチャの
    //    リポジトリ名 `octo-readme-rich` 自体が「readme」を含み誤ヒットする（大文字小文字を
    //    区別しないロール名照合の既知の落とし穴）。セクション見出しは id で一意に掴む。
    await expect(page.locator('#readme-heading')).toBeVisible()
    // フィクスチャの表（列数が多く横に長い）が実際に描画されていることを確認してから判定する。
    await expect(page.locator('.readme-content table')).toBeVisible()

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))

    expect(
      scrollWidth,
      `document.documentElement.scrollWidth(${scrollWidth}) <= clientWidth(${clientWidth})`,
    ).toBeLessThanOrEqual(clientWidth)
  })

  test('モバイル幅（375px 相当）でも body に横スクロールが出ない', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto(README_RICH_PATH)
    // 🔴 `getByRole('heading', { name: 'README' })` は部分一致のため、フィクスチャの
    //    リポジトリ名 `octo-readme-rich` 自体が「readme」を含み誤ヒットする（大文字小文字を
    //    区別しないロール名照合の既知の落とし穴）。セクション見出しは id で一意に掴む。
    await expect(page.locator('#readme-heading')).toBeVisible()
    await expect(page.locator('.readme-content table')).toBeVisible()

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))

    expect(
      scrollWidth,
      `375px 幅: document.documentElement.scrollWidth(${scrollWidth}) <= clientWidth(${clientWidth})`,
    ).toBeLessThanOrEqual(clientWidth)
  })
})
