import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import en from '../messages/en.json'

/**
 * SP-6 操作レビュー手順 1.「未検索の初期状態で、検索を促す表示が出ている」の回帰防止テスト
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-6`・対応 `AC-8`・`US-3`）。
 *
 * 🔴 初見フィードバック⑥（`content/discussions/first-impression-20260821/whiteboard.md`）対応:
 * `messages.home.idle` の「キーワードを入力して検索してください。」という文言は撤去された
 * （キーごと削除済み・`messages/ja.json` / `messages/en.json`）。未検索の初期状態は
 * 検索フォーム + 日次ダイジェスト（`SP-14`）だけで「検索を促す」役割を果たす。
 * あわせて「検索結果」見出し（`#results-heading`）とライブリージョン（`#search-status`）は
 * キーワード未入力時には DOM に一切描画されない（`app/[locale]/page.tsx` の `hasKeyword` 分岐）。
 */
test.describe('SP-6: 未検索の初期状態で検索を促す表示が出る', () => {
  test('ja: idle 文言は表示されず、検索欄・検索ボタンが同時に操作可能な状態で存在する', async ({
    page,
  }) => {
    await test.step('1. トップページ（/ja）をキーワードなしで開く', async () => {
      await page.goto('/ja')
      await expect(page).toHaveURL(/\/ja$/)
    })

    await test.step('2. 検索結果見出し・ライブリージョンは描画されない（撤去済みの idle 表示の回帰防止）', async () => {
      await expect(page.getByRole('heading', { name: ja.home.resultsHeading })).toHaveCount(0)
      await expect(page.locator('#search-status')).toHaveCount(0)
    })

    await test.step('3. 検索欄・検索ボタンが同時に操作可能な状態で存在する', async () => {
      const searchBox = page.getByRole('searchbox', { name: ja.home.searchLabel })
      const submitButton = page.getByRole('button', { name: ja.home.searchSubmit })
      await expect(searchBox).toBeEditable()
      await expect(submitButton).toBeEnabled()
    })
  })

  test('en: idle 文言は表示されず、検索欄・検索ボタンが同時に操作可能な状態で存在する', async ({
    page,
  }) => {
    await test.step('1. トップページ（/en）をキーワードなしで開く', async () => {
      await page.goto('/en')
      await expect(page).toHaveURL(/\/en$/)
    })

    await test.step('2. 検索結果見出し・ライブリージョンは描画されない（撤去済みの idle 表示の回帰防止）', async () => {
      await expect(page.getByRole('heading', { name: en.home.resultsHeading })).toHaveCount(0)
      await expect(page.locator('#search-status')).toHaveCount(0)
    })

    await test.step('3. 検索欄・検索ボタンが同時に操作可能な状態で存在する', async () => {
      const searchBox = page.getByRole('searchbox', { name: en.home.searchLabel })
      const submitButton = page.getByRole('button', { name: en.home.searchSubmit })
      await expect(searchBox).toBeEditable()
      await expect(submitButton).toBeEnabled()
    })
  })
})
