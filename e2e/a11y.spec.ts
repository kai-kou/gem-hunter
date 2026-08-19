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
})
