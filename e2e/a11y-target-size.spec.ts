import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor, uniqueKeyword } from './helpers'

/**
 * WCAG 2.2 SC 2.5.8 Target Size (Minimum) — Level AA（`docs/03_design/ui-ux/ui-ux-guidelines.md`
 * §2.4 / §7.5 が判定基準の正本。本ファイルは技法を実装手段として取り込むだけで、数値・例外の
 * 定義を重複させない）。Issue #53 の残作業（フォーカスインジケーター・320px リフローは実装済み・
 * Text Spacing は `e2e/a11y-text-spacing.spec.ts` が別途担当）。
 *
 * 判定は `locator.boundingBox()`（実描画サイズ）で行う。宣言値（クラス名の有無）では判定しない。
 * 注: `clip-path` でクリップされたターゲットは `boundingBox()` が元サイズを返すため検出できない
 * （本プロジェクトは現状 `clip-path` を使わない）。
 *
 * ## 対象の選定（`--size-control-xs` = 24px フロアを直接満たす方針・§7.5「間隔例外に頼らない」）
 * - **検索ボタン**（主要な操作要素・`--size-control-xl` = 44px）
 * - **ページ送りボタン**（前へ/次へ・`--size-control-md` = 32px）
 * - **カード内のリンク**（一覧の各行から詳細へ遷移する主リンク）
 * - **ヘッダーの言語切替リンク**（`LocaleSwitcher`・`--size-control-md` = 32px・Issue #844）
 * - **ヘッダーのログイン導線**（`LoginLink`・**ログイン / ログアウト両状態**を検証・
 *   `--size-control-sm` = 28px・Issue #844）。両状態は `className` こそ同じ
 *   `buttonVariants({ variant: 'ghost', size: 'sm' })` だが、要素種別（`<a>` / `<button>`）・
 *   ラベル文字列が異なり実描画サイズは別物になりうるため、片方の検証で他方を代表させない。
 *
 * ### ヘッダー 2 種を「間隔例外」ではなく対象へ追加する理由（Issue #844）
 * `back-link.tsx` の除外理由（「周囲に他の操作要素が無く直径 24px の円が誰とも重ならない」）は
 * ヘッダーには **流用できない**: `site-header.tsx:71` の右側グループ（`LocaleSwitcher` 全体 ↔
 * `LoginLink`）は `gap-2`（8px）、`locale-switcher.tsx:38` の `LocaleSwitcher` 内部（「日本語」↔
 * 「English」リンク同士）は `gap-1`（4px）でそれぞれ隣接しており、いずれの間隔でも Spacing 例外
 * （WCAG 2.2 SC 2.5.8 Exception 2: 24px 未満でも隣接ターゲットとの間に 24px 径の円が収まる間隔が
 * あれば可）が自然には成立しない。したがって除外側を選ぶには「間隔で救う」以外の根拠が要るが、
 * 実際には両者とも cva の size variant（`sm` = 28px / `default` = 32px）で 24px フロアを直接
 * 満たして描画されているため、除外ではなく §7.5 の検証対象へ加える（宣言 tier だけでなく実描画で
 * 担保する）。
 *
 * ## 対象から除外したもの（理由を明示する）
 * - **「一覧へ戻る」リンク**（`back-link.tsx`）: 独立した装飾のないテキストリンクで、周囲に
 *   他の操作要素が無く直径 24px の円が誰とも重ならない（Spacing 例外が自然に成立する配置）。
 *   本ファイルは §7.5 が明言する「間隔例外に頼らない」方針の検査を主眼とするため、既に
 *   フロアを直接満たすよう設計されている主要導線（上記の対象一覧）に対象を絞る。
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

  // `::after` の `position: absolute; inset: 0` は、値そのものが常に絶対長 `0px` を返すため、
  // 親 <li> が `position: relative`（positioned）でなければ containing block が親を指さず
  // 上記チェックが素通りしてしまう（`<li>` から `relative` が落ちても緑のまま、というトートロジー）。
  // ::after 検査の直後に、containing block の前提そのものを実測でアサートする。
  const liPosition = await li.evaluate((el) => getComputedStyle(el).position)
  expect(
    liPosition,
    `${label}: 親 <li> が positioned でないため ::after の containing block が親を指さない`,
  ).not.toBe('static')

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

  test('ヘッダーの言語切替リンクが 24×24 以上（実測は --size-control-md = 32px 相当）', async ({
    page,
  }) => {
    await page.goto('/ja')
    const nav = page.getByRole('navigation', { name: '言語切替' })
    const jaLink = nav.getByRole('link', { name: '日本語' })
    const enLink = nav.getByRole('link', { name: 'English' })
    await expect(jaLink).toBeVisible()
    await expect(enLink).toBeVisible()
    await expectTargetSizeAtLeast(jaLink, 'ヘッダー言語切替（日本語）')
    await expectTargetSizeAtLeast(enLink, 'ヘッダー言語切替（English）')
  })

  test('ヘッダーのログイン導線（未ログイン）が 24×24 以上（実測は --size-control-sm = 28px 相当）', async ({
    page,
  }) => {
    await page.goto('/ja')
    // `LoginLink` は未ログイン時は `<a href="/api/auth/login">`（`isAuthConfigured()` が真の
    // E2E 環境ではダミー OAuth 4 変数が揃うため、`showAuthLink` は常に true・`e2e/stub/e2e-env.mjs`）。
    const loginLink = page.getByRole('link', { name: ja.common.auth.login })
    await expect(loginLink).toBeVisible()
    await expectTargetSizeAtLeast(loginLink, 'ヘッダーのログイン導線（未ログイン）')
  })

  test('ヘッダーのログイン導線（ログイン済み＝ログアウトボタン）が 24×24 以上（実測は --size-control-sm = 28px 相当）', async ({
    page,
  }) => {
    // ログイン済み状態は `<form method="post" action="/api/auth/logout"><button type="submit">`
    // （`login-link.tsx`）で、未ログイン時の `<a href="/api/auth/login">` とは要素種別・ラベルが
    // 異なり実描画サイズは別物になりうる（Issue #844 指摘 1）。ログイン手順は
    // `e2e/sp-8-auth.spec.ts`「Step 0」を踏襲する（ダミー OAuth 経由で `/api/auth/login` へ
    // 遷移すると authorize → stub → callback → セッション Cookie 発行 → `/ja` までブラウザが
    // 自動でリダイレクトを辿る）。
    await page.goto('/api/auth/login')
    // `expect(page).toHaveURL()` ではなく `page.waitForURL()` を使う（前者はナビゲーション完了
    // ＝ Set-Cookie の反映を待たずに URL 一致を検出することがある・`sp-8-auth.spec.ts` と同じ理由）。
    await page.waitForURL(/\/ja(\?.*)?$/)

    const logoutButton = page.getByRole('button', { name: ja.common.auth.logout })
    await expect(logoutButton).toBeVisible()
    await expectTargetSizeAtLeast(
      logoutButton,
      'ヘッダーのログイン導線（ログイン済み＝ログアウト）',
    )
  })
})
