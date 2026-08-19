import { expect, test } from '@playwright/test'
import en from '../messages/en.json'
import ja from '../messages/ja.json'

/**
 * SP-6 操作レビュー手順 1.「未検索の初期状態で、検索を促す表示が出ている」の回帰防止テスト
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-6`・対応 `AC-8`・`US-3`）。
 *
 * `app/[locale]/page.tsx` は `state.status === 'idle'`（= キーワード未指定）のとき
 * `messages.home.idle` を表示する実装が既にあるが、それを検証する自動テストが存在しなかった。
 * 本ファイルは実装を変更せず、既存挙動をロケール別に固定する（`ja` / `en` の 2 系統）。
 */
test.describe('SP-6: 未検索の初期状態で検索を促す表示が出る', () => {
  test('ja: idle 文言が表示され、検索欄・検索ボタンが操作可能である', async ({ page }) => {
    await test.step('1. トップページ（/ja）をキーワードなしで開く', async () => {
      await page.goto('/ja')
      await expect(page).toHaveURL(/\/ja$/)
    })

    await test.step('2. idle 文言が表示されている', async () => {
      await expect(page.getByText(ja.home.idle, { exact: true })).toBeVisible()
    })

    await test.step('3. 検索欄・検索ボタンが同時に操作可能な状態で存在する', async () => {
      const searchBox = page.getByRole('searchbox', { name: ja.home.searchLabel })
      const submitButton = page.getByRole('button', { name: ja.home.searchSubmit })
      await expect(searchBox).toBeEditable()
      await expect(submitButton).toBeEnabled()
    })
  })

  test('en: idle 文言が表示され、検索欄・検索ボタンが操作可能である', async ({ page }) => {
    await test.step('1. トップページ（/en）をキーワードなしで開く', async () => {
      await page.goto('/en')
      await expect(page).toHaveURL(/\/en$/)
    })

    await test.step('2. idle 文言が表示されている', async () => {
      await expect(page.getByText(en.home.idle, { exact: true })).toBeVisible()
    })

    await test.step('3. 検索欄・検索ボタンが同時に操作可能な状態で存在する', async () => {
      const searchBox = page.getByRole('searchbox', { name: en.home.searchLabel })
      const submitButton = page.getByRole('button', { name: en.home.searchSubmit })
      await expect(searchBox).toBeEditable()
      await expect(submitButton).toBeEnabled()
    })
  })
})
