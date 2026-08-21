import { expect, test } from '@playwright/test'
import en from '../messages/en.json'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * Issue #347 T-5: ヘッダー共通化（一覧・詳細・404）の全ルート回帰テスト。
 * 設計は `content/discussions/ui_image_assets_20260821/whiteboard.md` round3
 * `frontend_arch`（§4「新規 E2E」）・round4 `lead` 最終合意が正本。
 *
 * `layout.tsx` からヘッダーを外したことで失う「h1 単一性のフレームワーク強制」を、
 * 全ルートで `header` 要素・`h1` 要素がちょうど 1 つであることを検証する本テストで置き換える
 * （frontend_arch round3 §4「R2 で言及した『フレームワーク保証→E2E 保証への置き換え』の実体」）。
 *
 * 404 到達時にヘッダーの言語切替・ログイン導線が存在することも検証する（既存の抜け漏れの
 * 回帰防止・タスク指示の明示要件）。
 */
test.describe('Issue #347: 全ルートで header/h1 がちょうど1つ・404 のヘッダー導線', () => {
  test('一覧（未検索）: header が1つ・h1 が1つ', async ({ page }) => {
    await page.goto('/ja')

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: ja.home.title })).toBeVisible()
  })

  test('一覧（検索後）: header が1つ・h1 が1つ', async ({ page }) => {
    await page.goto('/ja')
    await searchFor(page, 'react')
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: ja.home.title })).toBeVisible()
  })

  test('詳細（成功）: header が1つ・h1 が1つ', async ({ page }) => {
    await page.goto('/ja/repos/octostub/octo-widgets')
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: ja.home.title })).toBeVisible()
  })

  test('詳細（エラー: 存在しない owner/repo は not-found 経路。ここは検証済みの別ルートとして404で確認する）', async ({
    page,
  }) => {
    // 詳細ページのエラー分岐（レート制限・ネットワーク等）はスタブで恣意的に再現しにくいため、
    // 本テストでは既存 E2E（sp-9-errors.spec.ts）がカバーする範囲を前提に、
    // ここでは 404（DomainError の一種で最も再現が容易なエラー系）で header/h1 の単一性を確認する。
    const response = await page.goto('/ja/repos/does-not-exist-owner/does-not-exist-repo')
    expect(response?.status()).toBe(404)

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: ja.home.title })).toBeVisible()
  })

  test('404: header が1つ・h1 が1つ・言語切替とログイン導線が存在する', async ({ page }) => {
    const response = await page.goto('/ja/repos/does-not-exist-owner/does-not-exist-repo')
    expect(response?.status()).toBe(404)

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1, name: ja.home.title })).toBeVisible()

    const header = page.locator('header')
    // 言語切替導線（既存の抜け漏れの回帰防止・タスク指示の明示要件）
    await expect(
      header.getByRole('navigation', { name: ja.common.localeSwitcher.navLabel }),
    ).toBeVisible()
    await expect(
      header.getByRole('navigation', { name: ja.common.localeSwitcher.navLabel }).getByRole('link', {
        name: en.common.localeSwitcher.localeNames.en,
      }),
    ).toBeVisible()
    // ログイン導線（既存の抜け漏れの回帰防止・タスク指示の明示要件）
    await expect(header.getByRole('link', { name: ja.common.auth.login })).toBeVisible()
  })

  test('en/404: header が1つ・h1 が1つ・言語切替とログイン導線が存在する', async ({ page }) => {
    const response = await page.goto('/en/repos/does-not-exist-owner/does-not-exist-repo')
    expect(response?.status()).toBe(404)

    await expect(page.locator('header')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)

    const header = page.locator('header')
    await expect(
      header.getByRole('navigation', { name: en.common.localeSwitcher.navLabel }),
    ).toBeVisible()
    await expect(header.getByRole('link', { name: en.common.auth.login })).toBeVisible()
  })
})
