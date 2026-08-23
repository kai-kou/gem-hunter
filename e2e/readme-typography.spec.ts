import { expect, test, type Locator } from '@playwright/test'
import { tabUntilFocused } from './helpers'

/**
 * Issue #339: 詳細画面の README に書式を反映する回帰検査。
 *
 * 設計は `content/discussions/readme_typography_20260821/whiteboard.md` round3 `lead` の
 * 合意・裁定（争点 A〜F）が正本。現行の検査群（axe / Lighthouse / check_ui_dimensions.py /
 * check_contrast.py）は「書式が当たっていないこと」自体を検知できなかった（争点 F）ため、
 * 本ファイルは **クラス名の有無ではなく計算後スタイル（computed style）** を検証する。
 *
 * フィクスチャは `e2e/stub/server.mjs` の `octostub/octo-readme-rich`（README エンドポイントに
 * `readme-rich` を含むリポジトリ名を渡すと、見出し（h1〜h4）・段落・ネストした箇条書き・
 * 番号付きリスト・引用・リンクと `<strong>` を含む列数が多く横に長い表・長い行を含む
 * コードブロック・インラインコード・長い URL・バッジ画像を網羅した README HTML を返す）。
 *
 * README 本文コンテナは `class="readme-content prose ..."` を持つ契約（lane_style 実装）。
 * `.readme-content` を掴んで実効スタイルを取得する（クラス名の存在確認では終わらせない）。
 *
 * 🔴 Layer 1 セルフレビュー指摘対応（2026-08-21）: 旧版は `.prose h3`〜`h6` の上書きを丸ごと
 * 削除しても 6/6 緑のまま通っていた（h3 の実測値がページの h2 とたまたま 18px で一致していた
 * ことに加え、h4/h5/h6 の assertion が皆無だった）。また `--tw-prose-*` は本文色（body）以外
 * 実効検証されていなかった（headings を削除しても緑のまま）。以下を追加して塞ぐ:
 *   - h3 の実効サイズを固定値（`ui-ux-guidelines.md` §2.5 / `app/globals.css` の設計値）で検証
 *   - h3〜h6 の隣接レベル間でフォントサイズ or フォントウェイトが単調に減少することを検証
 *   - headings（h3）・links（a）・th/td-borders の実効値をサイトのトークンと突き合わせて検証
 *   - README 本文のスクロールコンテナ（`.readme-content`）がキーボードで到達可能であることを検証
 */

const README_RICH_PATH = '/ja/repos/octostub/octo-readme-rich'

/** `app/globals.css` `.prose h3`〜`h6`（§2.5 の設計値）の正本。ここが唯一の期待値の出所。 */
const HEADING_SCALE = {
  h3: { fontSizePx: 16, fontWeight: 700 },
  h4: { fontSizePx: 16, fontWeight: 600 },
  h5: { fontSizePx: 14, fontWeight: 600 },
  h6: { fontSizePx: 14, fontWeight: 500 },
} as const

/** 要素の実効フォントサイズ（px）とフォントウェイト（数値）をまとめて取得する。 */
async function measureFont(locator: Locator): Promise<{ fontSizePx: number; fontWeight: number }> {
  return locator.evaluate((el) => {
    const cs = getComputedStyle(el)
    return { fontSizePx: parseFloat(cs.fontSize), fontWeight: Number(cs.fontWeight) }
  })
}

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

    // 🔴 CRITICAL 指摘対応: 上記 2 つの相対比較だけでは `.prose h3`〜`h6` の上書きを
    //    丸ごと削除しても偶然通ってしまう（プラグイン既定の h3 が 18px でページの h2 と
    //    偶然一致するため）。設計値（`app/globals.css` `.prose h3`・§2.5）そのものを固定値で
    //    検証し、上書きが「効いていること」自体を担保する。
    await test.step('h3 の実効サイズが設計値（16px / font-weight 700）と一致する', async () => {
      const h3Font = await measureFont(readmeH3)
      expect(h3Font.fontSizePx, `README h3 の font-size`).toBe(HEADING_SCALE.h3.fontSizePx)
      expect(h3Font.fontWeight, `README h3 の font-weight`).toBe(HEADING_SCALE.h3.fontWeight)
    })
  })

  test('README 内の見出し（h3〜h6）は隣接レベル間でフォントサイズまたはフォントウェイトが単調に減少する', async ({
    page,
  }) => {
    // 🔴 CRITICAL 指摘対応: h4/h5/h6 に対する assertion が皆無だったため、`.prose h4`〜`h6`
    //    の上書きが削除されても検知できなかった。フィクスチャに raw h3/h4（+2 降格後の h5/h6）
    //    を追加した上で、4 段すべての実効値を隣接ペアで比較する。
    await page.goto(README_RICH_PATH)

    const levels = ['h3', 'h4', 'h5', 'h6'] as const
    const fonts = await Promise.all(
      levels.map(async (level) => {
        const el = page.locator(`.readme-content ${level}`).first()
        await expect(el, `README 内に ${level} が描画されていること`).toBeVisible()
        return { level, ...(await measureFont(el)) }
      }),
    )

    // 各レベルが設計値どおりであることも合わせて固定値で確認する（h3 は上のテストと重複するが、
    // 4 段をまとめて 1 箇所で見える化する狙いで再掲する）。
    for (const font of fonts) {
      const expected = HEADING_SCALE[font.level]
      expect(font.fontSizePx, `README ${font.level} の font-size`).toBe(expected.fontSizePx)
      expect(font.fontWeight, `README ${font.level} の font-weight`).toBe(expected.fontWeight)
    }

    for (let i = 1; i < fonts.length; i++) {
      const prev = fonts[i - 1]
      const cur = fonts[i]
      const detail = `${prev.level}(${prev.fontSizePx}px/${prev.fontWeight}) -> ${cur.level}(${cur.fontSizePx}px/${cur.fontWeight})`

      expect(cur.fontSizePx, `${detail}: font-size が増加していないこと`).toBeLessThanOrEqual(
        prev.fontSizePx,
      )
      expect(cur.fontWeight, `${detail}: font-weight が増加していないこと`).toBeLessThanOrEqual(
        prev.fontWeight,
      )
      // サイズ・ウェイトのどちらか一方は必ず狭義に減少する（両方が同値の「プラトー」＝
      // 視覚的に区別が付かない隣接レベルを許容しない）。
      const strictlyDecreased = cur.fontSizePx < prev.fontSizePx || cur.fontWeight < prev.fontWeight
      expect(strictlyDecreased, `${detail}: サイズ・ウェイトのいずれかは狭義に減少すること`).toBe(
        true,
      )
    }
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

    expect(
      readmeColor,
      `README 本文の色（${readmeColor}）がページ本文の色（${pageColor}）と一致`,
    ).toBe(pageColor)
  })

  // 🟡 WARNING 指摘対応: `--tw-prose-*`（18 項目）のうち本文色（--tw-prose-body）以外は
  // 実効検証が無く、`--tw-prose-headings` を丸ごと削除しても全検査が緑のまま通っていた
  // （レビュアーが実測）。headings（h3）・links（a）・th/td-borders の 3 項目を追加する。
  test('README 内の見出し（h3）の文字色がサイトの前景トークンと一致する', async ({ page }) => {
    await page.goto(README_RICH_PATH)

    const readmeH3 = page.locator('.readme-content h3').first()
    await expect(readmeH3).toBeVisible()

    // `--tw-prose-headings` は `var(--color-fg)`（= 本文と同じ前景トークン）へマッピングされる
    // 設計（`app/globals.css`）。基準値はページ本文（`document.body`）から取得する
    // （`--color-fg` を実際に描画している既存の実在要素・上の本文色テストと同じ手法）。
    const { headingColor, pageColor } = await readmeH3.evaluate((el) => ({
      headingColor: getComputedStyle(el).color,
      pageColor: getComputedStyle(document.body).color,
    }))

    expect(
      headingColor,
      `README h3 の色（${headingColor}）がページ本文の色（${pageColor}）と一致`,
    ).toBe(pageColor)
  })

  test('README 内のリンクの文字色がサイトのアクセントトークンと一致する', async ({ page }) => {
    await page.goto(README_RICH_PATH)

    // Layer 1 指摘対応でフィクスチャの表セルへリンクを追加した（`e2e/stub/server.mjs`）。
    // 本文中のリンク（長い URL の <a>）とあわせて、表セル内のリンクも実在することを確認する。
    const bodyLink = page.locator('.readme-content p a').first()
    const tableLink = page.locator('.readme-content table a').first()
    await expect(bodyLink).toBeVisible()
    await expect(tableLink).toBeVisible()

    // `--tw-prose-links` は `var(--color-accent)` へマッピングされる設計だが、本アプリの
    // UI コンポーネントは現時点でアクセントトークンを `color` として描画する箇所を持たない
    // （`text-accent` 等のユーティリティ未使用）ため、比較対象となる「既存の他要素」が無い。
    // そこで `--color-accent` を実際に `color` として適用した検証用ノードをその場で作り、
    // ブラウザ自身に解決させた実効値を基準にする（oklch 等の色関数を自前で変換しない・
    // `ui-ux-guidelines.md` §7.0「自前の oklch 変換式を二重実装しない」と同じ方針）。
    const { bodyLinkColor, tableLinkColor, accentTokenColor } = await page.evaluate(() => {
      const probe = document.createElement('span')
      probe.style.color = 'var(--color-accent)'
      probe.style.position = 'absolute'
      probe.style.visibility = 'hidden'
      document.body.appendChild(probe)
      const accentTokenColor = getComputedStyle(probe).color
      probe.remove()

      const body = document.querySelector('.readme-content p a')
      const table = document.querySelector('.readme-content table a')
      return {
        bodyLinkColor: body ? getComputedStyle(body).color : null,
        tableLinkColor: table ? getComputedStyle(table).color : null,
        accentTokenColor,
      }
    })

    expect(
      bodyLinkColor,
      `README 本文内リンクの色（${bodyLinkColor}）が --color-accent（${accentTokenColor}）と一致`,
    ).toBe(accentTokenColor)
    expect(
      tableLinkColor,
      `README 表内リンクの色（${tableLinkColor}）が --color-accent（${accentTokenColor}）と一致`,
    ).toBe(accentTokenColor)
  })

  test('README 内の表（th/td）の罫線色がサイトのボーダートークンと一致する', async ({ page }) => {
    await page.goto(README_RICH_PATH)

    const thead = page.locator('.readme-content table thead').first()
    // `tbody tr:last-child` は border-bottom-width が 0 になる仕様（typography プラグイン）
    // なので、罫線が実際に描画される先頭行（最終行ではない行）を対象にする。
    const firstBodyRow = page.locator('.readme-content table tbody tr').first()
    await expect(thead).toBeVisible()
    await expect(firstBodyRow).toBeVisible()

    // `--tw-prose-th-borders` / `--tw-prose-td-borders` はどちらも `var(--color-border)` へ
    // マッピングされる設計。基準値は `document.body` から取得する（グローバルリセット
    // `* { @apply border-border }` により、実際に描画される border-width の有無に関わらず
    // すべての要素の border-color として --color-border が既にセットされている実在の値）。
    const { theadBorderColor, tdBorderColor, pageBorderColor } = await page.evaluate(() => {
      const theadEl = document.querySelector('.readme-content table thead')
      const rowEl = document.querySelector('.readme-content table tbody tr')
      return {
        theadBorderColor: theadEl ? getComputedStyle(theadEl).borderBottomColor : null,
        tdBorderColor: rowEl ? getComputedStyle(rowEl).borderBottomColor : null,
        pageBorderColor: getComputedStyle(document.body).borderColor,
      }
    })

    expect(
      theadBorderColor,
      `thead の border-bottom-color（${theadBorderColor}）が --color-border（${pageBorderColor}）と一致`,
    ).toBe(pageBorderColor)
    expect(
      tdBorderColor,
      `tbody tr の border-bottom-color（${tdBorderColor}）が --color-border（${pageBorderColor}）と一致`,
    ).toBe(pageBorderColor)
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

  // 🟡 WARNING 指摘対応: 横溢れの受け皿である `.readme-content`（README 本文のスクロール
  // コンテナ）がマウス操作でしか到達できないと、キーボードのみの利用者は横溢れした表・
  // コードブロックの続きを読めない。fix_a11y 実装（他担当・同時進行）が `.readme-content` へ
  // `tabindex="0"` / `role="region"` / `aria-labelledby="readme-heading"` を付与する契約
  // （外側の `<section>` からは `aria-labelledby` が外れる）。属性の有無だけでなく、実際に
  // `Tab` キーでフォーカスが到達することまで確認する（`tabUntilFocused` は `e2e/helpers.ts`
  // の既存共通ヘルパー・`SP-10` 操作レビュー手順と同じ手法）。
  test('README 本文のスクロールコンテナ（.readme-content）はキーボードで到達できる', async ({
    page,
  }) => {
    await page.goto(README_RICH_PATH)

    const scrollContainer = page.locator('.readme-content')
    await expect(scrollContainer).toBeVisible()
    await expect(scrollContainer, '.readme-content の tabindex="0"').toHaveAttribute(
      'tabindex',
      '0',
    )
    await expect(scrollContainer, '.readme-content の role="region"').toHaveAttribute(
      'role',
      'region',
    )
    await expect(
      scrollContainer,
      '.readme-content の aria-labelledby="readme-heading"',
    ).toHaveAttribute('aria-labelledby', 'readme-heading')

    await tabUntilFocused(page, scrollContainer)
  })
})
