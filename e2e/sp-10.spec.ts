import { expect, test } from '@playwright/test'
import type { Locator } from '@playwright/test'
import {
  expectNoHorizontalScroll,
  measureFocusIndicator,
  searchFor,
  tabUntilFocused,
  uniqueKeyword,
} from './helpers'

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
  return uniqueKeyword('many-hits')
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
    // `generateMetadata`（app/[locale]/repos/[owner]/[repo]/page.tsx）の SSR タイトルを検証する。
    // 🔴 `toHaveTitle`（ハイドレーション後の document.title）だけでは検知できない: 同ページの
    // `SetDocumentTitle`（クライアント側 useEffect）が `generateMetadata` と完全に独立した
    // 経路（API 応答の `repository.fullName`）で同じ文言を書き込むため、`generateMetadata` を
    // 削除しても `document.title` は正しいまま残る（実測で確認済み・PR #183 レビュー指摘）。
    // JS 実行前の **初回レスポンス HTML** を直接取得して `<title>` を検証することで、
    // `generateMetadata` だけに依存する形にする。
    await expect(page).toHaveTitle(/octostub\/octo-widgets/)
    const ssrHtml = await (await page.request.get(page.url())).text()
    expect(ssrHtml, 'SSR 初回応答の <title> に owner/repo が含まれない').toMatch(
      /<title>[^<]*octostub\/octo-widgets[^<]*<\/title>/,
    )

    await tabUntilFocused(page, page.getByRole('link', { name: '一覧へ戻る' }))
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/\/ja(\?|$)/)
    // 戻ったとき検索条件（キーワード）が保持されている
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
  })

  test('手順0: 最初の Tab でスキップリンクへフォーカスが当たり、実行すると本文へ移動する（Issue #354）', async ({
    page,
  }) => {
    await page.goto('/ja')

    const skipLink = page.getByRole('link', { name: '本文へスキップ' })
    // 🔴 最初の Tab 1 回で到達すること自体を検証する（Bypass Blocks の要件は
    // 「本文より前にヘッダーのリンク群を Tab で通過させられない」こと）。
    await page.keyboard.press('Tab')
    await expect(skipLink).toBeFocused()

    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#main-content$/)

    const focusedId = await page.evaluate(() => document.activeElement?.id ?? null)
    expect(focusedId).toBe('main-content')
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

  test('手順4: フォーカスリングの実描画コントラストが 3:1 以上・太さ 2px 相当以上（PR #183 是正）', async ({
    page,
  }) => {
    // 🔴 これは「リングの有無」ではなく「リングの実効色・実効太さ」を見る層（`ui-ux-guidelines.md`
    // §7 の三層防御・層 3）。`tools/check_contrast.py`（層 1・宣言値のみ）と手順1の
    // 存在チェック（層 2・`boxShadow !== 'none'` のみ）はどちらも `ring-ring/50` のような
    // Tailwind ユーティリティ側の不透明度修飾子や `transition-all` の遷移途中値を検知できない
    // （SP-10 実測で判明・PR #183）。
    const MIN_CONTRAST = 3.0
    const MIN_WIDTH_PX = 2

    await page.goto('/ja')
    await searchFor(page, 'react')
    const detailLink = page.getByRole('link', { name: 'octostub/octo-widgets' })
    await expect(detailLink).toBeVisible()

    const resultsHeading = page.getByRole('heading', { name: '検索結果', level: 2 })
    const targets: Array<{ label: string; locator: Locator; focus: () => Promise<void> }> = [
      {
        label: '検索欄',
        locator: page.getByRole('searchbox', { name: '検索キーワード' }),
        focus: () =>
          tabUntilFocused(page, page.getByRole('searchbox', { name: '検索キーワード' })),
      },
      {
        label: '検索ボタン',
        locator: page.getByRole('button', { name: '検索' }),
        focus: () => tabUntilFocused(page, page.getByRole('button', { name: '検索' })),
      },
      {
        label: '一覧の詳細リンク',
        locator: detailLink,
        focus: () => tabUntilFocused(page, detailLink),
      },
      {
        // 🔴 `tabIndex={-1}`（page.tsx）のためキーボード Tab では到達しない。実アプリと同じ経路
        // （並べ替え・ページ送り後に `FocusOnNavigate` が呼ぶ programmatic `focus()`）で当てる。
        label: '結果見出し',
        locator: resultsHeading,
        focus: () => resultsHeading.evaluate((el) => (el as HTMLElement).focus()),
      },
    ]

    for (const { label, locator, focus } of targets) {
      await focus()
      const measurement = await measureFocusIndicator(page, locator)
      expect(
        measurement.kind,
        `${label}: フォーカスインジケータが検出できない ${JSON.stringify(measurement.raw)}`,
      ).not.toBe('none')
      expect(
        measurement.widthPx,
        `${label}: 太さ不足（実測 ${measurement.widthPx}px）${JSON.stringify(measurement)}`,
      ).toBeGreaterThanOrEqual(MIN_WIDTH_PX)
      expect(
        measurement.contrastRatio,
        `${label}: コントラスト不足（実測 ${measurement.contrastRatio.toFixed(2)}:1）${JSON.stringify(measurement)}`,
      ).toBeGreaterThanOrEqual(MIN_CONTRAST)
    }

    // 詳細ページの「一覧へ戻る」（ネイティブ <a>・back-link.tsx）も同じ基準で検査する。
    await tabUntilFocused(page, detailLink)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/repos\/octostub\/octo-widgets/)
    const backLink = page.getByRole('link', { name: '一覧へ戻る' })
    await tabUntilFocused(page, backLink)
    const backMeasurement = await measureFocusIndicator(page, backLink)
    expect(backMeasurement.kind, JSON.stringify(backMeasurement.raw)).not.toBe('none')
    expect(backMeasurement.widthPx, JSON.stringify(backMeasurement)).toBeGreaterThanOrEqual(
      MIN_WIDTH_PX,
    )
    expect(backMeasurement.contrastRatio, JSON.stringify(backMeasurement)).toBeGreaterThanOrEqual(
      MIN_CONTRAST,
    )
  })

  test('手順2/3 の前提: <meta name="viewport"> が SSR 応答に出力され、拡大を禁止していない', async ({
    page,
  }) => {
    // 🔴 Playwright の `setViewportSize` は CDP 経由でビューポートを直接設定するため、
    // `expectNoHorizontalScroll` 系のテストは `<meta name="viewport">` の実際の中身（例:
    // `maximum-scale` / `user-scalable=no` の誤混入）を検知できない死角がある（実測で確認済み・
    // PR #183 レビュー指摘）。実ブラウザ（モバイル）の挙動を左右するのは SSR 応答の
    // `<meta name="viewport">` そのものなので、JS 実行前の生 HTML を直接検証する。
    // 🔴 なお `app/[locale]/layout.tsx` の `viewport` export を丸ごと削除しても Next.js 16.3.1 は
    // 既定で同内容を自動出力するため（公式ドキュメント記載・実測で確認済み）、本テストが
    // 実際に退行として検知するのは「export の有無」ではなく「`maximum-scale` /
    // `user-scalable=no` の混入」（下記 2 行の assert）。
    const html = await (await page.request.get('/ja')).text()
    const match = html.match(/<meta[^>]*name="viewport"[^>]*>/)
    expect(match, 'SSR 応答に <meta name="viewport"> が無い').not.toBeNull()
    const viewportTag = match![0]
    expect(viewportTag).toContain('width=device-width')
    // WCAG 1.4.4（Resize Text）違反の再発防止（ui-ux-guidelines.md §2.4）。
    expect(viewportTag).not.toMatch(/user-scalable\s*=\s*no/)
    expect(viewportTag).not.toMatch(/maximum-scale/)
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
