import { expect, test } from '@playwright/test'
import en from '../messages/en.json'
import ja from '../messages/ja.json'

/**
 * SP-6 操作レビュー手順「存在しないリポジトリの URL を開く → Not Found 表示」の回帰防止テスト
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-6`・対応 `US-19` / `AC-5` 手順 4）。
 *
 * `app/[locale]/repos/[owner]/[repo]/page.tsx` は `repository === null` のとき既に `notFound()`
 * を呼んでいる（経路自体は実装済み）。本テストは「専用のロケール対応 404 UI が出る」こと
 * （`messages.detail.notFound` 文言・一覧への戻り導線）を検証する。
 *
 * スタブ GitHub API（`e2e/stub/server.mjs`）は fixtures に存在しない owner/repo に対して
 * 404 を返す（`not-found` を含む名前でなくても、フィクスチャに無ければ 404 になる）。
 */
test.describe('SP-6: 存在しないリポジトリの URL を開くと Not Found が表示される', () => {
  test('ja: detail.notFound 文言が表示され、一覧への戻り導線がある', async ({ page }) => {
    await test.step('1. 存在しない owner/repo の URL を直接開く', async () => {
      const response = await page.goto('/ja/repos/does-not-exist-owner/does-not-exist-repo')
      // notFound() は非ストリーミング応答で 404 を返す（file-conventions/not-found.md）
      expect(response?.status()).toBe(404)
    })

    await test.step('2. ロケール対応の Not Found 文言が表示されている', async () => {
      await expect(page.getByText(ja.detail.notFound, { exact: true })).toBeVisible()
    })

    await test.step('2.5. document title が Not Found 文言に変わる（ルートアナウンサーが沈黙しないための回帰防止・PR #127 指摘1）', async () => {
      await expect(page).toHaveTitle(ja.detail.notFound)
    })

    await test.step('2.6. 404 の装飾ビジュアル（Issue #347）が可視で存在する', async () => {
      await expect(page.locator('main img[src="/images/not-found.webp"]')).toBeVisible()
    })

    await test.step('3. 一覧への戻り導線があり、遷移すると一覧に戻る', async () => {
      await page.getByRole('link', { name: ja.detail.backLink }).click()
      await expect(page).toHaveURL(/\/ja$/)
      await expect(page.getByRole('searchbox', { name: ja.home.searchLabel })).toBeVisible()
    })
  })

  test('en: detail.notFound 文言が表示され、一覧への戻り導線がある', async ({ page }) => {
    await test.step('1. 存在しない owner/repo の URL を直接開く', async () => {
      const response = await page.goto('/en/repos/does-not-exist-owner/does-not-exist-repo')
      expect(response?.status()).toBe(404)
    })

    await test.step('2. ロケール対応の Not Found 文言が表示されている', async () => {
      await expect(page.getByText(en.detail.notFound, { exact: true })).toBeVisible()
    })

    await test.step('2.5. document title が Not Found 文言に変わる（ルートアナウンサーが沈黙しないための回帰防止・PR #127 指摘1）', async () => {
      await expect(page).toHaveTitle(en.detail.notFound)
    })

    await test.step('3. 一覧への戻り導線があり、遷移すると一覧に戻る', async () => {
      await page.getByRole('link', { name: en.detail.backLink }).click()
      await expect(page).toHaveURL(/\/en$/)
      await expect(page.getByRole('searchbox', { name: en.home.searchLabel })).toBeVisible()
    })
  })
})
