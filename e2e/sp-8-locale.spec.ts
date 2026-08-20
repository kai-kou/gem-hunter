import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * SP-8: 言語切替 UI（US-2）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-8` の操作レビュー手順「4. 言語切替」を
 * そのまま写す（`sprint-development-rules-detail.md` §2.6）。対応: `US-2` / `AR-4`。
 *
 * 🔴 このファイルが担当する範囲は言語切替 UI（`LocaleSwitcher`）のみ（whiteboard `sp8-auth-i18n-20260819`
 * 争点C・C-4）。`LocaleSwitcher` を `app/[locale]/layout.tsx` へ実際に配線する作業は
 * 統合担当が別途行うため、配線が済むまでは本ファイルは Red のまま（TDD の外側 Red・SD-2）。
 * `src/ui/locale-switcher.tsx` / `src/ui/url/build-locale-url.ts` 単体の Green は
 * ユニットテスト（併置 `*.test.ts(x)`）側で担保している。
 */
test('SP-8: 言語を英語に切り替えると URL のロケールと UI 文言が変わるが、リポジトリ説明文は原文のまま', async ({
  page,
}) => {
  await test.step('前提: 日本語 UI で検索し、結果一覧（説明文つき）が出ている', async () => {
    await page.goto('/ja')
    await searchFor(page, 'react')

    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
    // 検索結果の説明文（GitHub 由来データ）。機械翻訳しない対象であることの前提確認。
    await expect(
      page.getByText('Reusable UI widgets for octostub demos.', { exact: true }),
    ).toBeVisible()
    // 日本語 UI 文言（検索ボタン）
    await expect(page.getByRole('button', { name: '検索' })).toBeVisible()
  })

  await test.step('1. 言語切替 UI で English を選ぶ → URL のロケールが /en に変わる', async () => {
    await page
      .getByRole('navigation', { name: '言語切替' })
      .getByRole('link', { name: 'English' })
      .click()

    await expect(page).toHaveURL(/\/en(\?.*)?$/)
  })

  await test.step('2. UI 文言が英語になる', async () => {
    await expect(page.getByRole('button', { name: 'Search' })).toBeVisible()
    await expect(page.getByRole('searchbox', { name: 'Search keyword' })).toBeVisible()
  })

  await test.step('3. 検索条件（キーワード）を保ったまま切り替わっているため、結果一覧が引き続き表示される', async () => {
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
  })

  await test.step('4. リポジトリ説明文（GitHub 由来データ）は英語 UI でも原文のまま（機械翻訳しない・AR-4）', async () => {
    await expect(
      page.getByText('Reusable UI widgets for octostub demos.', { exact: true }),
    ).toBeVisible()
  })

  await test.step('5. 言語切替 UI で 日本語 に戻す → URL・UI 文言ともに元へ戻る', async () => {
    await page
      .getByRole('navigation', { name: 'Language' })
      .getByRole('link', { name: '日本語' })
      .click()

    await expect(page).toHaveURL(/\/ja(\?.*)?$/)
    await expect(page.getByRole('button', { name: '検索' })).toBeVisible()
  })
})
