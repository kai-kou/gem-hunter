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

  /**
   * Issue #347 T-5: 未検索状態と 404 は axe 未カバーだった（a11y_i18n round3 §5「新規 axe スキャン
   * 2 本」）。新規の装飾画像（`alt=""`）が axe の `image-alt` 等に抵触しないことをここで担保する。
   */
  test('未検索状態（/ja）に serious/critical の違反がない', async ({ page }) => {
    await page.goto('/ja')

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  test('404 画面に serious/critical の違反がない', async ({ page }) => {
    const response = await page.goto('/ja/repos/does-not-exist-owner/does-not-exist-repo')
    expect(response?.status()).toBe(404)

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })
})
