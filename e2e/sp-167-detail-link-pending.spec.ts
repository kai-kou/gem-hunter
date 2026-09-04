import { expect, test } from '@playwright/test'
import type { Locator, Page, Route } from '@playwright/test'
import { uniqueKeyword } from './helpers'

/**
 * Issue #167「詳細ページの読み込み中表示を、404 の HTTP ステータスを保ったまま実現する」の E2E。
 * 対応: `US-22`（読み込み中が伝わる）/ `AC-5`（存在しない詳細は 404 を返す）/ `AC-8`（読み込み中を判別できる）。
 *
 * 🔴 背景（この経路を選んだ理由）: 詳細ページは `AC-5` により `notFound()` を **同期的に** 返す必要が
 * あるため、`app/[locale]/repos/[owner]/[repo]/loading.tsx` を置けない（`loading.tsx` を置くと
 * ストリーミング応答になり HTTP ステータスが 200 に倒れる）。よって `US-22` は
 * **一覧 → 詳細へ遷移している間のクライアント側ペンディング表示**（`next/link` の `useLinkStatus`）で満たす。
 *
 * DOM 契約（実装役と共有済み・このテストが固定する）:
 *   - 一覧の各詳細リンク（`<Link href="/{locale}/repos/{owner}/{repo}">`）の **内側** に
 *     `data-testid="link-pending-hint"` / `aria-hidden="true"` の `<span>` が **常設** される
 *   - ペンディング中は `data-pending="true"`、それ以外は `data-pending="false"`
 *   - 可視性は `opacity` の切り替え（`display:none` にしない＝レイアウトシフトを起こさない）
 *
 * 🔴 #349 の規律: 「属性が付いているか」で終わらせず、`getComputedStyle` の **計算後の値**
 * （`opacity`）まで実測する。クラスは付くが CSS が当たっていない状態を素通りさせないため。
 */

/** 詳細ページへのナビゲーションを意図的に遅らせる幅（ms）。ペンディング表示を安定して観測するため。 */
const NAVIGATION_DELAY_MS = 5_000

/** 一覧ページ内の「詳細リンク」（`/{locale}/repos/{owner}/{repo}` を指す `<a>`）。 */
function detailLinks(page: Page): Locator {
  return page.locator('main ul li a[href*="/repos/"]')
}

function pendingHintOf(link: Locator): Locator {
  return link.locator('[data-testid="link-pending-hint"]')
}

/**
 * 詳細ページの document / RSC リクエストを遅延させる。
 *
 * 🔴 prefetch は握りつぶす（`route.abort()`）: `next/link` の既定 prefetch が完了していると
 * クリック後のペンディングが一瞬で終わり、観測が不安定になる。prefetch の失敗は Next.js 側で
 * 握られ、クリック時に本番の取得が改めて走る（＝この遅延の対象になる）。
 */
async function delayDetailNavigation(page: Page): Promise<void> {
  await page.route('**/repos/**', async (route: Route) => {
    if (route.request().headers()['next-router-prefetch'] === '1') {
      await route.abort()
      return
    }
    await new Promise((resolve) => setTimeout(resolve, NAVIGATION_DELAY_MS))
    await route.continue()
  })
}

test.describe('Issue #167: 一覧 → 詳細の遷移中にペンディング表示が出る', () => {
  test('初期状態では常設のヒントが data-pending="false" / opacity 0 で存在する（レイアウトシフト防止）', async ({
    page,
  }) => {
    await test.step('1. 一覧を表示する', async () => {
      await page.goto(`/ja?q=${uniqueKeyword('link-pending')}`)
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
    })

    await test.step('2. 各詳細リンクの内側にヒントが 1 つずつ常設されている', async () => {
      const links = detailLinks(page)
      const linkCount = await links.count()
      // 「対象 0 件でも成立する不変条件」を置かない（testing-strategy.md §7）ため、
      // まず対象が存在することを固定する。
      expect(linkCount, '詳細リンクが 1 件以上描画されていること').toBeGreaterThan(0)
      await expect(page.getByTestId('link-pending-hint')).toHaveCount(linkCount)

      for (let i = 0; i < linkCount; i++) {
        const hint = pendingHintOf(links.nth(i))
        await expect(hint).toHaveCount(1)
        await expect(hint).toHaveAttribute('data-pending', 'false')
        await expect(hint).toHaveAttribute('aria-hidden', 'true')
      }
    })

    await test.step('3. 非ペンディング時の計算後スタイルは opacity 0（かつ display は none でない）', async () => {
      const hint = pendingHintOf(detailLinks(page).first())
      const style = await hint.evaluate((el) => {
        const computed = getComputedStyle(el)
        return { opacity: computed.opacity, display: computed.display }
      })
      expect(Number(style.opacity)).toBe(0)
      // display:none にすると寸法が消えてペンディング時にレイアウトシフトする（契約違反）
      expect(style.display).not.toBe('none')
    })
  })

  test('詳細リンクをクリックすると data-pending="true" / opacity 1 になり、遷移後は詳細ページが表示される（US-22 / AC-5）', async ({
    page,
  }) => {
    await test.step('1. 一覧を表示し、詳細への遷移を遅延させる', async () => {
      await page.goto(`/ja?q=${uniqueKeyword('link-pending')}`)
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
      await delayDetailNavigation(page)
    })

    const link = page.getByRole('link', { name: 'octostub/octo-widgets' })
    const hint = pendingHintOf(link)

    await test.step('2. クリック直後、そのリンクのヒントがペンディングになる', async () => {
      await link.click()
      await expect(hint).toHaveAttribute('data-pending', 'true')
    })

    await test.step('3. 🔴 #349: 計算後の opacity が実際に 1 相当へ変わっている', async () => {
      await expect
        .poll(
          () => hint.evaluate((el) => Number(getComputedStyle(el).opacity)).catch(() => Number.NaN),
          { message: 'ペンディング中の hint は計算後 opacity が 1 相当であること' },
        )
        .toBeGreaterThan(0.9)
    })

    await test.step('4. 遅延が明けると詳細ページが表示される（404 にならない・回帰）', async () => {
      await expect(page).toHaveURL(/\/ja\/repos\/octostub\/octo-widgets/)
      await expect(
        page.getByRole('heading', { level: 2, name: /octostub\/octo-widgets/ }),
      ).toBeVisible()
    })
  })
})
