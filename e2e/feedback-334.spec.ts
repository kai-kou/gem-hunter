import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * Issue #334（初見フィードバック）F-1 / F-2 / F-3 / F-4 の操作レビュー。
 * 設計は `content/discussions/feedback334_detail_readme_20260821/whiteboard.md` round3
 * `lead` の合意・裁定が正本。
 *
 * F-1/F-2: ツールタイトル（共有ヘッダーの h1）をクリックすると、検索条件を捨てて
 *          `/{locale}`（未検索状態）へ遷移する。トップ・詳細のどちらからでも同じ挙動。
 * F-3: 詳細画面に概要（description）と最終更新日を追加する（一覧にあるのに詳細に無い状態の解消）。
 * F-4: 詳細画面で README が読める（Suspense 配下・失敗時は代替リンクへフォールバック）。
 */

test.describe('Issue #334: ツールタイトル導線 / 詳細画面の概要・最終更新・README', () => {
  test('F-1: トップで検索実行後にツールタイトルをクリックすると、検索条件を捨てて未検索状態へ戻る', async ({
    page,
  }) => {
    await test.step('検索を実行しておく', async () => {
      await page.goto('/ja')
      await searchFor(page, 'react')
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
      await expect(page).toHaveURL(/\/ja\?/)
    })

    await test.step('ツールタイトル（共有ヘッダーの h1）をクリックする', async () => {
      const titleLink = page.getByRole('banner').getByRole('link', { name: 'gem-hunter' })
      await expect(titleLink).toHaveAttribute('href', '/ja')
      await titleLink.click()
    })

    await test.step('クエリなしの /ja（未検索状態）へ遷移する', async () => {
      await expect(page).toHaveURL(/\/ja$/)
      // 未検索状態: 検索結果見出し・結果一覧が描画されない（page.tsx の hasKeyword 条件描画）。
      await expect(page.getByText('検索結果', { exact: true })).not.toBeVisible()
      await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue('')
    })
  })

  test('F-2: 詳細画面にもツールタイトルがあり、クリックすると未検索状態の /{locale} へ遷移する', async ({
    page,
  }) => {
    await page.goto('/ja/repos/octostub/octo-widgets?q=react&page=2&sort=stars&per_page=50')

    const titleLink = page.getByRole('banner').getByRole('link', { name: 'gem-hunter' })
    // 🔴 検索条件クエリを引き継がない（`buildSearchUrl` を経由しない固定 `/{locale}`）。
    await expect(titleLink).toHaveAttribute('href', '/ja')
    await titleLink.click()

    await expect(page).toHaveURL(/\/ja$/)
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue('')
  })

  test('F-3: 詳細画面に概要と最終更新日が表示される', async ({ page }) => {
    await page.goto('/ja/repos/octostub/octo-widgets')

    // フィクスチャ（octo-widgets）: description / pushed_at=2026-08-09T09:00:00Z
    await expect(page.getByText('Reusable UI widgets for octostub demos.')).toBeVisible()

    const updatedTerm = page.getByText('最終更新', { exact: true }).locator('xpath=ancestor::div[1]')
    await expect(updatedTerm.locator('dd')).toHaveText('2026/08/09')
  })

  test('F-4: 詳細画面で README 本文が読める', async ({ page }) => {
    await page.goto('/ja/repos/octostub/octo-widgets')

    await expect(page.getByRole('heading', { name: 'README' })).toBeVisible()
    await expect(
      page.getByText('README-STUB-CONTENT for octostub/octo-widgets.'),
    ).toBeVisible()
  })

  test('F-4: README が無いリポジトリでは代替リンクにフォールバックする（NFR-9: 内部エラーを出さない）', async ({
    page,
  }) => {
    await page.goto('/ja/repos/octostub/octo-readme-missing')

    // 詳細本体は通常どおり表示される（README の欠落が画面全体を落とさない）。
    await expect(
      page.getByRole('heading', { name: 'octostub/octo-readme-missing', exact: false }),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: 'GitHub で README を読む' })).toHaveAttribute(
      'href',
      'https://github.com/octostub/octo-readme-missing',
    )
    await expect(page.getByText('README-STUB-CONTENT')).toHaveCount(0)
  })
})
