import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * SP-9 操作レビュー手順 1.「該当のないキーワードで検索 → 0 件が明示される（読み込み中との区別がつく）」
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-9`・対応 `AC-8` / `US-22` / `US-23`）。
 *
 * 「読み込み中」と「0 件」は **別の要素・別の文言** で出す（同じ空欄に見えない）ことが要件なので、
 * 片方が出ているときにもう片方が出ていないことまで検証する。
 *
 * 読み込み中は一瞬で終わってしまうと観測できないため、スタブ（`e2e/stub/server.mjs`）の
 * `sp9-slow` マーカーで応答を 1.5 秒遅らせ、`waitUntil: 'commit'` でストリーミングの
 * 先頭（`<Suspense>` の fallback）を捕まえる。
 */

/**
 * 実行のたびに一意なキーワードを作る（`sp-5.spec.ts` / `ac-12-private.spec.ts` と同じ手口）。
 * キャッシュ（プロセス内共有・TTL あり）に前回試行の結果が残っていると、スタブの遅延分岐や
 * 0 件分岐まで到達せず観測できないため、構造的にキャッシュミスにする。
 */
function uniqueKeyword(prefix: string): string {
  return `${prefix}-${randomBytes(4).toString('hex')}`
}

test.describe('SP-9: 読み込み中と 0 件が区別できる', () => {
  test('読み込み中は role="status" の「読み込み中」で伝わり、結果が届くと消える（US-22）', async ({
    page,
  }) => {
    const keyword = uniqueKeyword('sp9-slow')

    await test.step('1. 応答が遅い検索を開き、ストリーミングの先頭を捕まえる', async () => {
      await page.goto(`/ja?q=${keyword}`, { waitUntil: 'commit' })
      const status = page.locator('main').getByRole('status')
      await expect(status).toContainText(ja.common.loading)
      await expect(status).toHaveAttribute('aria-live', 'polite')
    })

    await test.step('2. 見出しと検索欄は待ち時間中も表示されている（LCP 要素を隠さない）', async () => {
      await expect(page.getByRole('heading', { name: ja.home.title })).toBeVisible()
      await expect(page.getByRole('searchbox', { name: ja.home.searchLabel })).toBeVisible()
    })

    await test.step('3. 結果が届くと読み込み中表示が消える', async () => {
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
    })
  })

  test('0 件は該当なしの文言を role="status" で明示する（US-23 / US-26）', async ({ page }) => {
    await test.step('1. 該当のないキーワードで検索する', async () => {
      await page.goto('/ja')
      await searchFor(page, uniqueKeyword('zero-hits'))
    })

    await test.step('2. 0 件であることが明示され、読み込み中・エラーとは別物として出ている', async () => {
      const status = page.locator('main').getByRole('status')
      await expect(status).toContainText(ja.home.empty)
      // 読み込み中（US-22）と 0 件（US-23）を同じ表示にしない（AC-8）
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
      // 0 件はエラーではない（role="alert" にしない・ui-ux-guidelines.md §7.2）
      await expect(page.locator('main').getByRole('alert')).toHaveCount(0)
    })

    await test.step('3. 検索欄は残り、別のキーワードへ直せる', async () => {
      await expect(page.getByRole('searchbox', { name: ja.home.searchLabel })).toBeEditable()
    })
  })
})
