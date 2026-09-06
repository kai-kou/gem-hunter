import { expect, test } from '@playwright/test'

/**
 * Issue #858: `app/globals.css` の `--font-sans: var(--font-sans);`（自己参照）により
 * Tailwind v4 の `@theme inline` が無効値を黙って無視し（fail-open）、`html { @apply font-sans; }`
 * が UA 既定フォントへフォールバックしていた回帰検査。
 *
 * `app/[locale]/layout.tsx` は `next/font/google` の `Geist` を `--font-geist-sans` という
 * CSS 変数名で `<html>` に注入している。実測（本 Issue 修正時）では、next/font が解決する
 * 実効 `font-family` 値は `Geist, "Geist Fallback"`（フォント名自体は固定文字列 "Geist"。
 * クラス名がハッシュ化されるのは `next/font` のスコープ用クラスであって、フォント名文字列
 * 自体ではない）。本テストは **クラス名・宣言値ではなく計算後の値**（`getComputedStyle`）で、
 * UA 既定フォント（例: "Times New Roman"）へフォールバックしておらず実際に Geist へ解決
 * されていることを検証する（`ui-ux-guidelines.md` §7.5 / `e2e/sp-167-detail-link-pending.spec.ts`
 * の規律に従う）。
 */

test.describe('Issue #858: --font-sans の自己参照によるフォント未適用の回帰検査', () => {
  test('html / body の実効 font-family が next/font の Geist に解決される', async ({ page }) => {
    await page.goto('/ja')

    const [htmlFontFamily, bodyFontFamily] = await Promise.all([
      page.evaluate(() => getComputedStyle(document.documentElement).fontFamily),
      page.evaluate(() => getComputedStyle(document.body).fontFamily),
    ])

    expect(htmlFontFamily, `html の実効 font-family: ${htmlFontFamily}`).toMatch(/Geist/)
    expect(bodyFontFamily, `body の実効 font-family: ${bodyFontFamily}`).toMatch(/Geist/)
  })

  test('--font-sans CSS 変数が自己参照のまま残っておらず、Geist へ解決されている', async ({
    page,
  }) => {
    await page.goto('/ja')

    const fontSansValue = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--font-sans').trim(),
    )

    // 自己参照（`var(--font-sans)` 相当・または空文字）のままではないことを確認する。
    expect(fontSansValue, `--font-sans の実効値: "${fontSansValue}"`).not.toBe('')
    expect(fontSansValue, `--font-sans の実効値: "${fontSansValue}"`).not.toContain(
      'var(--font-sans)',
    )
    expect(fontSansValue, `--font-sans の実効値: "${fontSansValue}"`).toMatch(/Geist/)
  })

  test('--font-heading CSS 変数も同じく Geist へ解決されている', async ({ page }) => {
    await page.goto('/ja')

    const fontHeadingValue = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--font-heading').trim(),
    )

    expect(fontHeadingValue, `--font-heading の実効値: "${fontHeadingValue}"`).not.toBe('')
    expect(fontHeadingValue, `--font-heading の実効値: "${fontHeadingValue}"`).toMatch(/Geist/)
  })
})
