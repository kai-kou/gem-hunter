import { expect, test } from '@playwright/test'
import type { Result } from 'axe-core'
import { createAxeBuilder } from './axe'
import { searchFor } from './helpers'

/**
 * NFR-26: 自動アクセシビリティ検査（一覧画面・詳細画面）。
 * 品質ゲートは「Lighthouse Accessibility 100」相当のため、重大度 serious / critical の
 * 違反を 0 件とする（minor / moderate は本テストの対象外）。
 */
function seriousOrCritical(violations: Result[]): Result[] {
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
}

test.describe('NFR-26: axe 自動アクセシビリティ検査', () => {
  test('一覧画面（検索結果）に serious/critical の違反がない', async ({ page }) => {
    await page.goto('/ja')
    await searchFor(page, 'react')
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  test('詳細画面に serious/critical の違反がない', async ({ page }) => {
    await page.goto('/ja/repos/octostub/octo-widgets')
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  /**
   * Issue #339 Layer 1 指摘対応（WARNING）: 既存の axe スイートは `octo-widgets`（表もコード
   * ブロックも持たない最小フィクスチャ）にしか当たっておらず、実際に横溢れが起きる
   * `octo-readme-rich`（`e2e/readme-typography.spec.ts` と同じフィクスチャ）にはこれまで axe が
   * 一度も走っていなかった。スクロール領域（`.readme-content` の `role="region"` /
   * `aria-labelledby` / `tabindex`）まわりの a11y 退行はここでのみ機械検知できる。
   */
  test('README の書式が反映された詳細画面（横溢れ・スクロール領域）に serious/critical の違反がない', async ({
    page,
  }) => {
    await page.goto('/ja/repos/octostub/octo-readme-rich')
    // 🔴 リポジトリ名自体が「readme」を含むため `getByRole('heading', { name: 'README' })`
    //    は誤ヒットする（`e2e/readme-typography.spec.ts` と同じ既知の落とし穴）。
    //    セクション見出しは id で一意に掴む。
    await expect(page.locator('#readme-heading')).toBeVisible()
    // 横に長い表が実際に描画されている（＝スクロール領域が実在する）ことを確認してから判定する。
    await expect(page.locator('.readme-content table')).toBeVisible()

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  /**
   * Issue #334 F-1/F-2: 共有ヘッダーの導入で h1 が重複しないことを確認する（whiteboard
   * `feedback334_detail_readme_20260821` round3 lead 裁定「1 ページ 1 h1 を保つ」）。
   * トップページの自前 h1 撤去・詳細画面の 3 箇所（RepositoryDetail / DomainError 分岐 /
   * not-found.tsx）の h2 降格が漏れると、ここで h1 が 2 つ検出されて落ちる。
   */
  test('一覧画面の h1 は 1 つだけ（共有ヘッダーのツールタイトル）', async ({ page }) => {
    await page.goto('/ja')
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: 'gem-hunter' })).toBeVisible()
  })

  test('詳細画面の h1 は 1 つだけ（リポジトリ名は h2 へ降格）', async ({ page }) => {
    await page.goto('/ja/repos/octostub/octo-widgets')
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: 'gem-hunter' })).toBeVisible()
  })
})
