import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Result } from 'axe-core'
import ja from '../messages/ja.json'
import { createAxeBuilder } from './axe'
import { searchFor } from './helpers'

/**
 * SP-9 操作レビュー手順 4.「スクリーンリーダーで各状態が読み上げられる」
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-9`・対応 `AC-8` / `US-26` / `NFR-12`）。
 *
 * スクリーンリーダーそのものは自動テストで動かせないため、**支援技術へ届く条件**
 * （ライブリージョンの role と `aria-live`）を DOM で検証し、あわせて axe で
 * 重大な違反が無いことを確認する（`a11y.spec.ts` と同じ基準）。
 *
 * 役割分担（`ui-ux-guidelines.md` §7.2）:
 *   読み込み中・0 件 → `role="status"`（暗黙で polite）／エラー → `role="alert"`
 */
function uniqueKeyword(prefix: string): string {
  return `${prefix}-${randomBytes(4).toString('hex')}`
}

function seriousOrCritical(violations: Result[]): Result[] {
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
}

test.describe('SP-9: 各状態が支援技術に伝わる', () => {
  test('0 件の状態が role="status" で伝わり、axe に重大な違反がない（US-23 / US-26）', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueKeyword('zero-hits'))

    await expect(page.locator('main').getByRole('status')).toContainText(ja.home.empty)

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  test('エラーの状態が role="alert" で伝わり、axe に重大な違反がない（US-24 / US-26）', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueKeyword('sp9-network-down'))

    const alert = page.locator('main').getByRole('alert')
    await expect(alert).toContainText(ja.common.errors.network)
    // role="alert" は暗黙で assertive。同一要素へ aria-live を重ねない
    // （iOS VoiceOver の二重読み上げ回避・ui-ux-guidelines.md §7.2）
    await expect(alert).not.toHaveAttribute('aria-live', /.*/)

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  test('読み込み中の状態が role="status" + aria-live="polite" で伝わる（US-22 / US-26）', async ({
    page,
  }) => {
    await page.goto(`/ja?q=${uniqueKeyword('sp9-slow')}`, { waitUntil: 'commit' })

    const status = page.locator('main').getByRole('status')
    await expect(status).toContainText(ja.common.loading)
    await expect(status).toHaveAttribute('aria-live', 'polite')
  })

  test('読み込み中の状態にも axe の重大な違反がない（US-22 / US-26）', async ({ page }) => {
    await page.goto(`/ja?q=${uniqueKeyword('sp9-slow')}`, { waitUntil: 'commit' })
    await expect(page.locator('main').getByRole('status')).toContainText(ja.common.loading)

    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  /**
   * 🔴 `ui-ux-guidelines.md` §7.2「ライブリージョンは初期 DOM に空で常設し、中身を書き換える。
   * 要素ごと動的挿入しない」の回帰テスト（SP-9 セルフレビュー指摘 1）。
   *
   * ライブリージョンが `<Suspense>` の **中** にあると、読み込み完了時にリージョン要素ごと
   * 差し替わる。支援技術は「新しく挿入された要素」を読み上げないため、
   * 「読み込み中 → 件数」の遷移が一切通知されない。要素の identity（同一 DOM ノードか）で
   * これを検出する。
   */
  test('ライブリージョンは読み込み中と結果表示で同一要素のまま（中身だけ書き換わる・NFR-12）', async ({
    page,
  }) => {
    await page.goto(`/ja?q=${uniqueKeyword('sp9-slow')}`, { waitUntil: 'commit' })

    const region = page.locator('#search-status')
    await expect(region).toContainText(ja.common.loading)

    const handle = await region.elementHandle()
    expect(handle, 'ライブリージョンが初期 DOM に存在すること').not.toBeNull()

    // 結果が届くまで待つ（ライブリージョンの中身が件数表示へ書き換わる）
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
    await expect(region).not.toContainText(ja.common.loading)

    const isSameNode = await page.evaluate(
      (element) => element.isConnected && element === document.getElementById('search-status'),
      handle,
    )
    expect(isSameNode, 'ライブリージョン要素が差し替わらずに残っていること').toBe(true)

    // エラー（role="alert"）をライブリージョンへ入れ子にしない（§7.2）
    await expect(region.getByRole('alert')).toHaveCount(0)
  })
})
