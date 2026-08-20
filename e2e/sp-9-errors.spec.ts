import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * SP-9 操作レビュー手順 2. / 3.（`docs/02_requirements/user-story-map.md` §5.3 `SP-9`）:
 *   2. ネットワークを遮断して検索 → 「接続できません」+ 再試行手段
 *   3. レート制限をモックで再現 → 復帰時刻とログイン導線が出る（他のエラーと文言が違う）
 * 対応: `AC-8` / `US-24` / `US-25` / `prd.md` §7（エラー種別の判別仕様）。
 *
 * 🔴 ネットワーク遮断は `page.route()` では再現できない。GitHub API を叩くのは **サーバー側**
 * （Server Component → `GithubRepositoryQuery`）であり、ブラウザのリクエスト経路に乗らないため。
 * 代わりにスタブ（`e2e/stub/server.mjs`）へ `sp9-network-down` マーカーを足し、応答を書かずに
 * 接続を切ることで `fetch` 自体の失敗（到達不可）を再現する（`NFR-24`: 外部 API はモック化）。
 *
 * 🔴 画面に出るのは **種別から引いた文言** であり、`Error.message`（開発者向け）ではない
 * （`NFR-9` / Issue #107）。そのため各テストは「種別ごとに文言が違うこと」を相互に確認する。
 */

function uniqueKeyword(prefix: string): string {
  return `${prefix}-${randomBytes(4).toString('hex')}`
}

/** `<main>` 内のエラー通知（Next.js のルートアナウンサーも role="alert" を持つため範囲を絞る）。 */
function errorNotice(page: import('@playwright/test').Page) {
  return page.locator('main').getByRole('alert')
}

test.describe('SP-9: エラーは種別ごとに区別され、再試行手段が示される', () => {
  test('ネットワーク到達不可: 接続できない旨 + 再試行リンクが出る（US-24）', async ({ page }) => {
    const keyword = uniqueKeyword('sp9-network-down')

    await test.step('1. 上流へ到達できない状況で検索する', async () => {
      await page.goto('/ja')
      await searchFor(page, keyword)
    })

    await test.step('2. 「接続できませんでした」相当の文言が role="alert" で出る', async () => {
      await expect(errorNotice(page)).toContainText(ja.common.errors.network)
    })

    await test.step('3. 再試行手段（同じ検索をやり直すリンク）が示される', async () => {
      const retry = page.locator('main').getByRole('link', { name: ja.common.retry })
      await expect(retry).toBeVisible()
      await expect(retry).toHaveAttribute('href', `/ja?q=${keyword}`)
      await retry.click()
      await expect(page).toHaveURL(new RegExp(`/ja\\?q=${keyword}$`))
      await expect(errorNotice(page)).toContainText(ja.common.errors.network)
    })

    await test.step('4. レート制限固有の案内は出ない（種別で文言が違う）', async () => {
      await expect(errorNotice(page)).not.toContainText(ja.common.errors.rateLimitPrimaryLoginHint)
    })
  })

  test('一次レート制限: 復帰時刻とログイン導線が出る（US-25 / AR-5）', async ({ page }) => {
    await test.step('1. レート制限を返すキーワードで検索する', async () => {
      await page.goto('/ja')
      await searchFor(page, uniqueKeyword('rate-limit'))
    })

    await test.step('2. 復帰時刻（時刻表記）が本文に補間されている', async () => {
      const alert = errorNotice(page)
      // `x-ratelimit-reset` から算出した復帰時刻。固定値にできないため時刻の形で確認する
      await expect(alert).toContainText(/\d{1,2}:\d{2}/)
      // プレースホルダーが未置換のまま出ていない（NFR-9: 内部表現を出さない）
      await expect(alert).not.toContainText('{resetAt}')
    })

    await test.step('3. ログインで枠を増やせる案内とログイン導線が出る（AR-5 唯一の価値訴求点）', async () => {
      await expect(errorNotice(page)).toContainText(ja.common.errors.rateLimitPrimaryLoginHint)
      const loginLink = page.locator('main').getByRole('link', { name: ja.common.auth.login })
      await expect(loginLink).toBeVisible()
      await expect(loginLink).toHaveAttribute('href', '/api/auth/login')
    })

    await test.step('4. 他のエラー種別とは文言が違う（AC-8）', async () => {
      const alert = errorNotice(page)
      await expect(alert).not.toContainText(ja.common.errors.network)
      await expect(alert).not.toContainText(ja.common.errors.upstream)
    })
  })

  test('二次レート制限: 再試行までの秒数が出て、ログイン導線は出ない（prd.md §7）', async ({
    page,
  }) => {
    await test.step('1. 二次レート制限（retry-after あり）を返すキーワードで検索する', async () => {
      await page.goto('/ja')
      await searchFor(page, uniqueKeyword('sp9-secondary-rate-limit'))
    })

    await test.step('2. スタブが返した retry-after（30 秒）が本文に出る', async () => {
      await expect(errorNotice(page)).toContainText(
        ja.common.errors.rateLimitSecondary.replace('{retryAfterSeconds}', '30'),
      )
    })

    await test.step('3. 一次レート制限のログイン導線は出ない（枠の枯渇ではないため）', async () => {
      await expect(errorNotice(page)).not.toContainText(ja.common.errors.rateLimitPrimaryLoginHint)
      await expect(
        page.locator('main').getByRole('link', { name: ja.common.auth.login }),
      ).toHaveCount(0)
    })
  })

  test('GitHub 側の障害（5xx）: 上流障害の文言 + 再試行手段が出る（prd.md §7）', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueKeyword('upstream-error'))

    await expect(errorNotice(page)).toContainText(ja.common.errors.upstream)
    await expect(page.locator('main').getByRole('link', { name: ja.common.retry })).toBeVisible()
    await expect(errorNotice(page)).not.toContainText(ja.common.errors.network)
  })

  test('詳細ページのエラーも種別ベースの文言 + 再試行手段になる（US-24）', async ({ page }) => {
    const repo = `rate-limit-${randomBytes(4).toString('hex')}`

    await test.step('1. 取得がレート制限で失敗する詳細 URL を開く', async () => {
      await page.goto(`/ja/repos/octostub/${repo}`)
    })

    await test.step('2. 種別に対応した文言とログイン導線が出る（内部メッセージは出さない）', async () => {
      await expect(errorNotice(page)).toContainText(ja.common.errors.rateLimitPrimaryLoginHint)
      await expect(errorNotice(page)).not.toContainText('stub:')
    })

    await test.step('3. 再試行手段と一覧への戻り導線があり、行き止まりにならない', async () => {
      await expect(
        page.locator('main').getByRole('link', { name: ja.common.retry }),
      ).toHaveAttribute('href', `/ja/repos/octostub/${repo}`)
      await page.getByRole('link', { name: ja.detail.backLink }).click()
      await expect(page).toHaveURL(/\/ja$/)
    })
  })
})
