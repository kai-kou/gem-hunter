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
})
