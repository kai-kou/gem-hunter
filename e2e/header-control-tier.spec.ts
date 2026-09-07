import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { measureControlTier } from './helpers'

/**
 * Issue #842: ヘッダーの `LoginLink` を `size: 'sm'`（28px / `text-[0.8rem]`=12.8px）から
 * `size: 'default'`（`--size-control-md` = 32px / `text-sm` = 14px）へ引き上げ、隣接する
 * `LocaleSwitcher`（既に `size: 'default'`）と同一 tier に揃えた回帰検査。
 *
 * `e2e/a11y-target-size.spec.ts` は WCAG 2.5.8 の 24px フロアを満たすかどうかだけを検証する
 * （tier が sm=28px でも md=32px でもどちらもフロアは満たすため、tier が sm へ巻き戻っても
 * あのファイルの既存テストは検知できない）。本ファイルは「tier が LocaleSwitcher と揃っているか」
 * という別の関心事を検証する（分割理由: あのファイル冒頭の JSDoc が定める対象選定基準は
 * フロア判定に閉じており、tier 整合はその基準に含まれないため新規ファイルへ切り出した。
 * `e2e/font-family.spec.ts` 等、テーマ別に薄く切り出す既存の分割慣行に合わせる）。
 *
 * `docs/rules/sprint-development-rules.md` SD-2「実装が効いていることを実効値で確かめる」に
 * 従い、クラス名の有無ではなく `getComputedStyle` の計算後の値で検証し、LocaleSwitcher との
 * 相対比較だけでなく設計値（32px / 14px）の固定値でも検証する（相対比較だけだと、スケールを
 * 丸ごと失っても両者が偶然同じ値のまま一致してすり抜ける）。
 */

const EXPECTED_HEIGHT = '32px'
const EXPECTED_FONT_SIZE = '14px'

test.describe('Issue #842: ヘッダーの LoginLink が LocaleSwitcher と同一 tier（32px/14px）', () => {
  test('未ログイン: ログイン導線が LocaleSwitcher と同一 tier で描画される', async ({ page }) => {
    await page.goto('/ja')

    const nav = page.getByRole('navigation', { name: '言語切替' })
    const localeLink = nav.getByRole('link', { name: '日本語' })
    const loginLink = page.getByRole('link', { name: ja.common.auth.login })
    await expect(localeLink).toBeVisible()
    await expect(loginLink).toBeVisible()

    const localeTier = await measureControlTier(localeLink)
    const loginTier = await measureControlTier(loginLink)

    // 固定値（設計値）での検証: 相対比較だけだと tier をまとめて失っても偶然一致しうる。
    expect(loginTier.height, `ログイン導線の高さ（実測 ${loginTier.height}）`).toBe(EXPECTED_HEIGHT)
    expect(loginTier.fontSize, `ログイン導線のフォントサイズ（実測 ${loginTier.fontSize}）`).toBe(
      EXPECTED_FONT_SIZE,
    )
    expect(localeTier.height, `LocaleSwitcher の高さ（実測 ${localeTier.height}）`).toBe(
      EXPECTED_HEIGHT,
    )
    expect(
      localeTier.fontSize,
      `LocaleSwitcher のフォントサイズ（実測 ${localeTier.fontSize}）`,
    ).toBe(EXPECTED_FONT_SIZE)

    // 相対比較（tier が LocaleSwitcher と揃っていること自体の直接検証）。
    expect(loginTier.height, 'ログイン導線と LocaleSwitcher の高さが不一致').toBe(localeTier.height)
    expect(loginTier.fontSize, 'ログイン導線と LocaleSwitcher のフォントサイズが不一致').toBe(
      localeTier.fontSize,
    )
  })

  test('ログイン済み: ログアウトボタンも LocaleSwitcher と同一 tier で描画される', async ({
    page,
  }) => {
    // ログイン手順は `e2e/a11y-target-size.spec.ts`「ヘッダーのログイン導線（ログイン済み＝
    // ログアウトボタン）」を踏襲する（ダミー OAuth 経由で `/api/auth/login` へ遷移すると
    // authorize → stub → callback → セッション Cookie 発行 → `/ja` までブラウザが自動で
    // リダイレクトを辿る）。`page.waitForURL()` を使うのも同ファイルと同じ理由
    // （`expect(page).toHaveURL()` は Set-Cookie の反映を待たずに URL 一致を検出することがある）。
    await page.goto('/api/auth/login')
    await page.waitForURL(/\/ja(\?.*)?$/)

    const nav = page.getByRole('navigation', { name: '言語切替' })
    const localeLink = nav.getByRole('link', { name: '日本語' })
    const logoutButton = page.getByRole('button', { name: ja.common.auth.logout })
    await expect(localeLink).toBeVisible()
    await expect(logoutButton).toBeVisible()

    const localeTier = await measureControlTier(localeLink)
    const logoutTier = await measureControlTier(logoutButton)

    expect(logoutTier.height, `ログアウトボタンの高さ（実測 ${logoutTier.height}）`).toBe(
      EXPECTED_HEIGHT,
    )
    expect(
      logoutTier.fontSize,
      `ログアウトボタンのフォントサイズ（実測 ${logoutTier.fontSize}）`,
    ).toBe(EXPECTED_FONT_SIZE)
    expect(logoutTier.height, 'ログアウトボタンと LocaleSwitcher の高さが不一致').toBe(
      localeTier.height,
    )
    expect(logoutTier.fontSize, 'ログアウトボタンと LocaleSwitcher のフォントサイズが不一致').toBe(
      localeTier.fontSize,
    )
  })
})
