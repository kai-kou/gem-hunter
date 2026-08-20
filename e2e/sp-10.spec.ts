import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { searchFor, tabUntilFocused } from './helpers'

/**
 * SP-10: 誰でも操作できる（`docs/02_requirements/user-story-map.md` §5.3 `SP-10`）。
 * 操作レビュー手順 1〜3 をそのまま E2E に写す（`SD-2`）。対応: `US-15` / `E-13` / `E-14` /
 * `E-15` / `E-16` / `E-17`・`AC-9`。
 *
 * 着手前の議論（`content/discussions/sp10_a11y_20260820/whiteboard.md`）で確定した契約:
 * - 結果見出し: `page.getByRole('heading', { name: '検索結果', level: 2 })`（R2 実装）
 * - ライブリージョン: `page.locator('main').getByRole('status')`（R2 実装）
 * - 一覧のオーナーアイコンは `alt=""`（R3 実装・アクセシブルネームを持たない）
 * - 詳細ページの `document.title` に `octostub/octo-widgets` が含まれる（R2/R3 実装）
 *
 * R2/R3 の実装完了前は一部が Red のままでよい（TDD の Red・契約先行）。
 */

function uniqueManyHitsKeyword(): string {
  return `many-hits-${randomBytes(4).toString('hex')}`
}

/**
 * 「破綻しない」の述語: 横スクロールが発生しない
 * （`document.scrollingElement` の `clientWidth` は縦スクロールバー分を既に除いた値なので、
 * スクロールバー由来の偽陽性は原理的に発生しない）。
 */
async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }
  })
  // +1px は sub-pixel 丸め対策
  expect(overflow.scrollWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(
    overflow.clientWidth + 1,
  )
}

test.describe('SP-10: 誰でも操作できる', () => {
  test('手順1: キーボードのみで 検索 → 一覧 → 詳細 → 一覧 を完走でき、フォーカスが常に見える', async ({
    page,
  }) => {
    const keyword = 'react'
    await page.goto('/ja')

    await tabUntilFocused(page, page.getByRole('searchbox', { name: '検索キーワード' }))
    await page.keyboard.type(keyword)
    await page.keyboard.press('Enter')

    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    await tabUntilFocused(page, page.getByRole('link', { name: 'octostub/octo-widgets' }))

    // フォーカスの可視性: 到達時に outline または box-shadow が 'none' でないこと。
    // 🔴 自動化の限界: これは「リング（相当のもの）が存在するか」の構造チェックにとどまる。
    // リング自体の色・コントラストの後退（#179 クラス）はここでは検知できない
    // （静的トークン検査 `tools/check_contrast.py` が担当する層・
    // `docs/03_design/ui-ux/ui-ux-guidelines.md` §7 の三層防御を参照）。
    const focusVisibility = await page.evaluate(() => {
      const el = document.activeElement
      if (el === null) return null
      const style = getComputedStyle(el)
      return { outlineStyle: style.outlineStyle, boxShadow: style.boxShadow }
    })
    expect(focusVisibility, '到達先要素が取得できなかった').not.toBeNull()
    expect(
      focusVisibility?.outlineStyle !== 'none' || focusVisibility?.boxShadow !== 'none',
      JSON.stringify(focusVisibility),
    ).toBe(true)

    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/repos\/octostub\/octo-widgets/)
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()

    await tabUntilFocused(page, page.getByRole('link', { name: '一覧へ戻る' }))
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/\/ja(\?|$)/)
    // 戻ったとき検索条件（キーワード）が保持されている
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
  })

  test('フォーカス喪失の検知: ページ送り後もフォーカスが body へ落ちない', async ({ page }) => {
    const keyword = uniqueManyHitsKeyword()
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)

    await tabUntilFocused(
      page,
      page
        .getByRole('navigation', { name: '検索結果のページ' })
        .getByRole('link', { name: '次のページへ' }),
    )
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/[?&]page=2(&|$)/)

    // 🔴 弱い assert: 「フォーカスが body へ落ちていないか」のみを見る（喪失の検知）。
    // R2 が結果見出し（`page.getByRole('heading', { name: '検索結果', level: 2 })`）へ
    // `tabIndex={-1}` + `focus()` を実装したら、`tabUntilFocused(page, 結果見出し)` の
    // 「実際にどこへ着地したか」を見る強い assert へ格上げする（2 段階運用。
    // `content/discussions/sp10_a11y_20260820/whiteboard.md` round2 e2e_verify 譲歩・
    // round3 lead 判定 D-2）。
    await expect
      .poll(() => page.evaluate(() => document.activeElement === document.body))
      .toBe(false)
  })

  const viewports = [
    {
      label: 'スマートフォン幅（375px）',
      size: { width: 375, height: 667 },
    },
    {
      label: '200% 拡大相当（640×360）',
      size: { width: 640, height: 360 },
    },
  ] as const

  for (const { label, size } of viewports) {
    test(`手順2/3: ${label} で一覧（検索前）・一覧（検索後）・詳細のいずれも横スクロールが発生しない`, async ({
      page,
    }) => {
      // 200% 拡大の再現手段は viewport 幅を半分にする案を採用（1280px の既定を基準に 640px）。
      // `deviceScaleFactor` / `--force-device-scale-factor` は CSS px のレイアウト幅を変えず
      // reflow を検証できないため不採用、CSS `zoom` の注入は「ブラウザズームへの対応」ではなく
      // 「zoom プロパティへの対応」を測ってしまい fixed 要素等で偽陽性/偽陰性を生むため不採用
      // （whiteboard round1 e2e_verify・round3 lead 判定）。
      // スマートフォン幅（375px）とは別 viewport として明確に区別する（別 SC・別意図）。
      await page.setViewportSize(size)

      await test.step('一覧（検索前）', async () => {
        await page.goto('/ja')
        await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toBeVisible()
        await expectNoHorizontalScroll(page)
      })

      await test.step('一覧（検索後）', async () => {
        await searchFor(page, 'react')
        await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
        await expectNoHorizontalScroll(page)
      })

      await test.step('詳細', async () => {
        await page.getByRole('link', { name: 'octostub/octo-widgets' }).click()
        await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()
        await expectNoHorizontalScroll(page)
      })
    })
  }
})
