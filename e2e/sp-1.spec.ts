import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'

/**
 * SP-1: キーワードで GitHub を検索し、結果が一覧で見える。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-1` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応 AC: `AC-1` / `AC-2`（一部）/ `AC-3`（必達部分）。
 */
test('SP-1: 検索して一覧が出る', async ({ page }) => {
  await test.step('1. トップページを開く', async () => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/ja(\?.*)?$/)
  })

  await test.step('2. 検索欄に react と入力し、ボタン（または Enter）で実行する', async () => {
    await searchFor(page, 'react')
    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.keyword}=react(&|$)`))
  })

  await test.step('3. オーナーアイコンとリポジトリ名の一覧が出る', async () => {
    // 各カードは topics も `<ul>/<li>` で表示するため、getByRole('listitem') は
    // ネストした topics の項目まで拾ってしまう。結果一覧の直接の子だけを数える。
    const items = page.getByRole('list').first().locator(':scope > li')
    await expect(items).toHaveCount(3)

    // リポジトリ名（AC-3・独立 URL への遷移リンクとしても機能する）
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'octostub/octo-forms' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'octostub/octo-charts' })).toBeVisible()

    // オーナーアイコン（アクセシブルな名前はオーナーの login）
    await expect(page.getByRole('img', { name: 'octostub' }).first()).toBeVisible()
  })
})
