import { expect, test, type Page } from '@playwright/test'

/**
 * SP-3: 一覧 → 詳細 → 一覧の往復が通る。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-3` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応 AC: `AC-4`（表示項目は `AC-5`）。
 */

/** 詳細ページの `<dt>` ラベルに対応する `<dd>` の表示値を読む（AC-5 検証用）。 */
async function readStat(page: Page, label: string): Promise<string> {
  const dt = page.getByText(label, { exact: true })
  const container = dt.locator('xpath=ancestor::div[1]')
  return (await container.locator('dd').innerText()).trim()
}

test('SP-3: 詳細まで往復できる', async ({ page }) => {
  await test.step('前提: 検索結果を表示しておく（SP-1）', async () => {
    await page.goto('/ja')
    await page.getByRole('searchbox', { name: '検索キーワード' }).fill('react')
    await page.getByRole('button', { name: '検索' }).click()
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
  })

  let detailUrl = ''

  await test.step('1. 一覧のカードを選ぶ → 独立した URL の詳細ページへ遷移する（モーダルではない）', async () => {
    await page.getByRole('link', { name: 'octostub/octo-widgets' }).click()
    await expect(page).toHaveURL(/\/ja\/repos\/octostub\/octo-widgets$/)
    detailUrl = page.url()

    // モーダルでないことの検証: dialog が存在せず、遷移元の検索フォームも
    // このページには存在しない（同一 DOM 上のオーバーレイではなく別ページへのフルナビゲーション）
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByRole('search')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()
  })

  await test.step('2. その URL を直接開く / リロードする → 同じ内容が出る', async () => {
    await page.reload()
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()

    await page.goto(detailUrl)
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()
  })

  await test.step('3. 戻る導線で一覧へ戻る', async () => {
    await page.getByRole('link', { name: '一覧へ戻る' }).click()
    await expect(page).toHaveURL(/\/ja$/)
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toBeVisible()
  })

  await test.step('AC-5: Star 数と Watcher 数が別の数字になっている', async () => {
    await page.goto('/ja/repos/octostub/octo-widgets')

    const starValue = await readStat(page, 'star 数')
    const watcherValue = await readStat(page, 'watcher 数')

    // フィクスチャ（octo-widgets）: stargazers_count=1240 / subscribers_count=96
    expect(starValue).toBe('1,240')
    expect(watcherValue).toBe('96')
    expect(starValue).not.toBe(watcherValue)
  })
})
