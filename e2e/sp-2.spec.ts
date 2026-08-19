import { expect, test } from '@playwright/test'
import { createAxeBuilder } from './axe'

/**
 * SP-2: URL とロケールの形が決まる。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-2` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応 AC: `AC-2`（URL 部分）。
 *
 * 手順 2「キーワードとページが URL に乗る」について: 検索フォーム自体はページ番号の入力を
 * 持たない（ページネーション UI は `SP-7` の担当・`US-7`）。そのため「キーワードが URL に
 * 乗ること」はフォーム送信で検証し、「ページが URL に乗ること（= `page` パラメータが尊重され、
 * URL 直書きで往復できること）」は `SEARCH_PARAM_KEYS.page`（`src/ui/url/search-params.ts`）に
 * 従って URL を直接書き換えて検証する。
 */
test('SP-2: URL とロケールの形が決まる', async ({ page, context }) => {
  await test.step('1. `/` を開く → `/ja` へリダイレクトされる', async () => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/ja$/)
  })

  await test.step('2. 検索を実行する → キーワードとページが URL に乗る', async () => {
    await page.getByRole('searchbox', { name: '検索キーワード' }).fill('react')
    await page.getByRole('button', { name: '検索' }).click()
    await expect(page).toHaveURL(/\/ja\?q=react$/)

    const pageTwoUrl = new URL(page.url())
    pageTwoUrl.searchParams.set('page', '2')
    await page.goto(pageTwoUrl.pathname + pageTwoUrl.search)
    await expect(page).toHaveURL(/[?&]q=react(&|$)/)
    await expect(page).toHaveURL(/[?&]page=2(&|$)/)
    // ページ 2 のフィクスチャ（e2e/fixtures/repos.json の 4 件目以降）が出ていることで
    // page パラメータが実際に効いていることを確認する
    await expect(page.getByRole('link', { name: 'octostub/octo-tables' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'octostub/octo-icons' })).toBeVisible()
  })

  await test.step('3. アドレスバーの URL をコピーし、別タブで開く → 同じ結果が再現する', async () => {
    const copiedUrl = page.url()
    const newTab = await context.newPage()
    try {
      await newTab.goto(copiedUrl)
      await expect(newTab.getByRole('link', { name: 'octostub/octo-tables' })).toBeVisible()
      await expect(newTab.getByRole('link', { name: 'octostub/octo-icons' })).toBeVisible()
    } finally {
      await newTab.close()
    }
  })

  await test.step('4. 主要な文字と背景のコントラスト比が 4.5:1 以上である（axe: color-contrast）', async () => {
    const results = await createAxeBuilder(page).withRules('color-contrast').analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
  })
})
