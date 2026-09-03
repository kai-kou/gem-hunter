import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll, searchFor, uniqueKeyword } from './helpers'

/**
 * 横スクロール退行ガード（`NFR-15` / WCAG 2.2 SC 1.4.10 Reflow）。
 *
 * 背景: 本番の検索結果で、GitHub の `description` に含まれる長い URL が折り返されず
 * ページ全体に横スクロールが発生した。`e2e/sp-10.spec.ts` にも同じ述語
 * （`document.scrollingElement` の `scrollWidth <= clientWidth`）はあったが、
 * **既定スタブの文字列がどれも短く改行機会を含んでいた**ため検知できなかった。
 * ここでは「改行機会がゼロの連続長文字列」を含む専用データセット
 * （`e2e/stub/server.mjs` のマーカー `overflow-guard`）を 320px 幅で描画して検証する。
 *
 * 議論記録: `content/discussions/horizontal_overflow_20260823/whiteboard.md`
 *
 * 🔴 viewport は **320px 単独**。320 CSS px は SC 1.4.10 の達成基準文言に名指しされた唯一の
 * 閾値であり、改行不能文字列に必要な幅は viewport 幅に依存せず一定なので、
 * 320 を通れば 375 / 430 は論理的に導ける（固定幅ブレークポイントを使わない
 * `ui-ux-guidelines.md` §3 の制約が前提）。
 *
 * 🔴 `body` / `html` に `overflow-x: hidden` / `clip` を足してはならない（理由は
 * `expectNoHorizontalScroll`（`e2e/helpers.ts`）のコメント）。
 */

function uniqueOverflowGuardKeyword(): string {
  return uniqueKeyword('overflow-guard')
}

test.describe('横スクロール退行ガード（NFR-15 / SC 1.4.10）', () => {
  test.use({ viewport: { width: 320, height: 720 } })

  test('320px 幅で、折り返せない長文字列を含む検索結果を出しても横スクロールが発生しない', async ({
    page,
  }) => {
    await page.goto('/ja')
    await expectNoHorizontalScroll(page, '検索前のトップ')

    await searchFor(page, uniqueOverflowGuardKeyword())

    // 3 件（長い URL 入り description / 長い単一 topic / 長いリポジトリ名）がすべて描画されるのを待つ。
    await expect(
      page.getByRole('link', { name: 'octostub/overflow-guard-description' }),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: 'octostub/overflow-guard-topic' })).toBeVisible()
    await expect(
      page.getByRole('link', { name: `octostub/overflow-guard-${'n'.repeat(48)}` }),
    ).toBeVisible()

    await expectNoHorizontalScroll(page, '検索結果一覧')
  })

  test('320px 幅で、折り返せない長文字列を含む詳細ページを開いても横スクロールが発生しない', async ({
    page,
  }) => {
    await page.goto('/ja')
    await searchFor(page, uniqueOverflowGuardKeyword())

    await page.getByRole('link', { name: 'octostub/overflow-guard-description' }).click()
    await expect(
      page.getByRole('heading', { name: /octostub\/overflow-guard-description/ }),
    ).toBeVisible()

    await expectNoHorizontalScroll(page, '詳細ページ（長い URL 入り description）')
  })

  test('横スクロールを検知した際、診断情報（culprit）に発生源要素の情報が埋まる（#831 回帰ガード）', async ({
    page,
  }) => {
    // `findWidestElement`（helpers.ts）は expectNoHorizontalScroll の失敗時にしか実行されない
    // 経路のため、このテストが無いと将来の変更で壊れても誰も気づかない。意図的に横溢れを起こす
    // 要素を注入し、`expectNoHorizontalScroll` が投げる診断情報（culprit）の各フィールドが
    // 発生源要素を正しく指しているかを検証する。
    await page.goto('/ja')

    await page.evaluate(() => {
      const probe = document.createElement('div')
      probe.id = 'overflow-guard-diagnostic-probe'
      // 前後・連続空白入りの class 属性（helpers.ts のセレクタ組み立てが空要素を混入させないことも兼ねて検証）
      probe.className = '  diagnostic-probe   marker  '
      probe.style.position = 'absolute'
      probe.style.left = '0'
      probe.style.top = '0'
      probe.style.width = '500px'
      probe.style.height = '1px'
      document.body.appendChild(probe)
    })

    let caught: Error | undefined
    try {
      await expectNoHorizontalScroll(page, '診断プローブ')
    } catch (error) {
      caught = error as Error
    }

    expect(caught).toBeInstanceOf(Error)
    const message = caught?.message ?? ''
    // `expect(value, message)` の message は 1 行の JSON（`JSON.stringify` は改行を入れない）。
    // Playwright がその後ろに Expected/Received 等を追記するため、1 行分だけを正規表現で切り出す。
    const jsonLine = /\{.*\}/.exec(message)?.[0] ?? ''
    const detail = JSON.parse(jsonLine) as {
      culprit: {
        selector: string
        textExcerpt: string
        right: number
        fontFamily: string
        letterSpacing: string
      } | null
    }

    expect(detail.culprit).not.toBeNull()
    // セレクタに空 class（連続・前後空白由来）が混入していない（`..` を含まない）ことを確認
    expect(detail.culprit?.selector).toBe(
      'div#overflow-guard-diagnostic-probe.diagnostic-probe.marker',
    )
    expect(detail.culprit?.right).toBeGreaterThanOrEqual(499)
    expect(detail.culprit?.fontFamily.length).toBeGreaterThan(0)
    expect(typeof detail.culprit?.letterSpacing).toBe('string')
  })
})
