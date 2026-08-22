import { test, type Page } from '@playwright/test'

/**
 * スライド 2・3 に貼る実 UI スクリーンショットを撮る。
 *
 * 議論 `project-slides-20260822` の verdict（`content/slides_plan.json` の `screenshots`）で
 * 「AI 生成の概念図ではなく実画面を見せる」と決めたことの実装。
 *
 * 🔴 スマホ表示を主役、PC 表示を添えとして 1 枚に合成する（飼い主の指示・2026-08-22）ため、
 * ここでは素材だけを `images/raw/` に撮り、合成は `compose_screenshots.py` が行う。
 *
 * 表示されるリポジトリは実データではなく `e2e/stub/server.mjs` のスタブ（外部ネットワーク非依存で
 * 決定論的に撮るため）。スタブのオーナーアバターは 1x1 の透明 PNG で、アプリが付ける `?s=N`
 * （`INF-11`）と噛み合わず壊れた画像アイコンとして描画されるため、撮影時だけ無彩色の
 * プレースホルダへ差し替える（装飾画像・`alt=""`・`ui-ux-guidelines.md` §7.4 なので意味は変わらない）。
 */
const OUT = 'content/slides/project-explanation-20260822/images/raw'

const AVATAR_PLACEHOLDER =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">' +
      '<rect width="64" height="64" rx="32" fill="#d4d4d8"/></svg>',
  )

async function replaceStubAvatars(page: Page): Promise<void> {
  await page.evaluate((placeholder) => {
    for (const img of Array.from(document.querySelectorAll('img'))) {
      // スタブの 1x1 透明 PNG（`e2e/stub/server.mjs`）だけを対象にする。
      if (img.getAttribute('src')?.startsWith('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB')) {
        img.setAttribute('src', placeholder)
      }
    }
  }, AVATAR_PLACEHOLDER)
}

test('shot-01: 検索結果一覧', async ({ page }, testInfo) => {
  await page.goto('/ja?q=react')
  // 一覧の最初のカードが描画されるまで待つ（レイアウト確定前に撮らない）。
  await page.getByRole('link', { name: 'octostub/octo-widgets' }).waitFor()
  await replaceStubAvatars(page)
  await page.screenshot({ path: `${OUT}/shot-01-${testInfo.project.name}.png` })
})

test('shot-02: 今日の Gem ダイジェスト', async ({ page }, testInfo) => {
  // `?date=` は `getDailyDigest` の並び替えシード。固定日付で再現性を担保する（ADR 0014 §2.2）。
  await page.goto('/ja?date=20260820')
  await page.getByRole('heading', { name: '今日の Gem', level: 2 }).waitFor()
  await replaceStubAvatars(page)
  // 既定の表示位置ではヒーロー画像が画面を占め、ダイジェストが 5 件とも入らない。
  // 見出しが上部に来る位置までスクロールしてから撮る（折り返し量が違うので端末ごとに調整する）。
  const offset = testInfo.project.name === 'mobile' ? 430 : 330
  await page.evaluate((y) => window.scrollTo(0, y), offset)
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${OUT}/shot-02-${testInfo.project.name}.png` })
})
