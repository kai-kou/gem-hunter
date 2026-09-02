import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { searchFor, uniqueKeyword } from './helpers'

/**
 * WCAG 2.2 SC 2.5.8 Target Size (Minimum) — Level AA（`docs/03_design/ui-ux/ui-ux-guidelines.md`
 * §2.4 / §7.5 が判定基準の正本。本ファイルは技法を実装手段として取り込むだけで、数値・例外の
 * 定義を重複させない）。Issue #53 の残作業（フォーカスインジケーター・320px リフローは実装済み・
 * Text Spacing は `e2e/a11y-text-spacing.spec.ts` が別途担当）。
 *
 * 判定は `locator.boundingBox()`（実描画サイズ）で行う。宣言値（クラス名の有無）では判定しない。
 *
 * ## 対象の選定（`--size-control-xs` = 24px フロアを直接満たす方針・§7.5「間隔例外に頼らない」）
 * - **検索ボタン**（主要な操作要素・`--size-control-xl` = 44px）
 * - **ページ送りボタン**（前へ/次へ・`--size-control-md` = 32px）
 * - **カード内のリンク**（一覧の各行から詳細へ遷移する主リンク）
 *
 * ## 対象から除外したもの（理由を明示する）
 * - **「一覧へ戻る」リンク**（`back-link.tsx`）: 独立した装飾のないテキストリンクで、周囲に
 *   他の操作要素が無く直径 24px の円が誰とも重ならない（Spacing 例外が自然に成立する配置）。
 *   本ファイルは §7.5 が明言する「間隔例外に頼らない」方針の検査を主眼とするため、既に
 *   フロアを直接満たすよう設計されている主要導線（上記 3 種）に対象を絞る。
 * - **検索欄（input）**: WCAG の User Agent Control 例外の議論はあるが、本プロジェクトの
 *   設計トークンは input にも `--size-control-xl` を適用しており（`search-form.tsx`）、
 *   実質は上記ボタン群と同じ検証になるため重複を避けて対象に含めない。
 * - **本文中のインラインリンク**（Inline 例外）: このフィクスチャ（README スタブ）には
 *   段落内リンクが存在するが、Inline 例外そのものに該当するため最初から対象外
 *   （`readme-typography.spec.ts` 等の他ファイルの担当領域でもある）。
 */

const MIN_TARGET_PX = 24

async function expectTargetSizeAtLeast(locator: Locator, label: string): Promise<void> {
  const box = await locator.boundingBox()
  expect(box, `${label}: boundingBox が取得できない（非表示か DOM に存在しない）`).not.toBeNull()
  expect(box!.width, `${label}: 幅不足（実測 ${box!.width}px）`).toBeGreaterThanOrEqual(
    MIN_TARGET_PX,
  )
  expect(box!.height, `${label}: 高さ不足（実測 ${box!.height}px）`).toBeGreaterThanOrEqual(
    MIN_TARGET_PX,
  )
}

/**
 * カード内リンクは `after:absolute after:inset-0`（`repository-list.tsx` の実装コメント参照）で
 * クリック領域を親 `<li>` 全体へ拡張する意図的な技法（`ui-ux-guidelines.md` §4.3）。
 * `<a>` 自身の boundingBox は見出しテキストぶんの小さい矩形のままなので、まず ::after が
 * 実際に `position: absolute` + 4 辺 0 で親を覆っていることを実測で確認したうえで、
 * 実効クリック領域である親 `<li>` の boundingBox を判定対象にする（宣言値のクラス名では
 * なく、両方とも `getComputedStyle` / `boundingBox()` の実測値で確認する）。
 */
async function expectExpandedCardTargetSize(link: Locator, label: string): Promise<void> {
  const afterCoversParent = await link.evaluate((el) => {
    const after = getComputedStyle(el, '::after')
    return (
      after.position === 'absolute' &&
      after.top === '0px' &&
      after.right === '0px' &&
      after.bottom === '0px' &&
      after.left === '0px'
    )
  })
  expect(
    afterCoversParent,
    `${label}: ::after によるクリック領域拡張（position:absolute; inset:0）が検出できない。` +
      '拡張が無いなら <a> 自身が 24×24 を満たす必要がある（本関数の前提が崩れている）',
  ).toBe(true)

  const li = link.locator('xpath=ancestor::li[1]')
  await expectTargetSizeAtLeast(li, `${label}（拡張後のクリック領域＝親 <li>）`)
}

function uniquePaginationKeyword(): string {
  return uniqueKeyword('many-hits')
}

test.describe('SC 2.5.8 Target Size (Minimum): 主要な操作要素が 24×24 CSS px 以上', () => {
  test('検索ボタンが 24×24 以上（実測は --size-control-xl = 44px 相当）', async ({ page }) => {
    await page.goto('/ja')
    const searchButton = page.getByRole('button', { name: '検索' })
    await expect(searchButton).toBeVisible()
    await expectTargetSizeAtLeast(searchButton, '検索ボタン')
  })

  test('ページ送りボタン（前へ/次へ）が 24×24 以上（実測は --size-control-md = 32px 相当）', async ({
    page,
  }) => {
    const keyword = uniquePaginationKeyword()
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)

    const nav = page.getByRole('navigation', { name: '検索結果のページ' })
    const nextLink = nav.getByRole('link', { name: '次のページへ' })
    await expect(nextLink).toBeVisible()
    await expectTargetSizeAtLeast(nextLink, 'ページ送りボタン（次へ）')

    await nextLink.click()
    await expect(page).toHaveURL(/[?&]page=2(&|$)/)
    const prevLink = nav.getByRole('link', { name: '前のページへ' })
    await expect(prevLink).toBeVisible()
    await expectTargetSizeAtLeast(prevLink, 'ページ送りボタン（前へ）')
  })

  test('カード内のリンク（一覧 → 詳細）は ::after 拡張後のクリック領域（親 <li>）が 24×24 以上', async ({
    page,
  }: {
    page: Page
  }) => {
    await page.goto('/ja')
    await searchFor(page, 'react')
    const detailLink = page.getByRole('link', { name: 'octostub/octo-widgets' })
    await expect(detailLink).toBeVisible()
    await expectExpandedCardTargetSize(detailLink, 'カード内のリンク（octo-widgets）')
  })
})
