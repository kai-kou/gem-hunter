import { test, type Page } from '@playwright/test'

/**
 * スライド 2〜4 に貼る実 UI スクリーンショットを撮る。
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

/**
 * Gem 一覧（`src/ui/gem-list.tsx`）の avatar は `https://github.com/{owner}.png` を **直接** 参照する
 * （`AR-11`: 候補プールのシャードに avatar_url 相当の列が無いため）。撮影環境は外部ネットワークへ
 * 出られないので、`e2e/sp-19.spec.ts` と同じ方針で `page.route()` により常に同じ画像を返す。
 * こちらは資料に載る画像なので、1x1 透明 PNG ではなく上の無彩色プレースホルダをそのまま返す。
 */
async function stubOwnerAvatars(page: Page): Promise<void> {
  await page.route('https://github.com/**.png**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body:
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">' +
        '<rect width="64" height="64" rx="32" fill="#d4d4d8"/></svg>',
    }),
  )
}

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

/**
 * 🔴 検索語に `gem-badge` を含めるのは **スタブの分岐条件**（`e2e/stub/server.mjs` の
 * `GEM_BADGE_MARKER`）だからで、撮影のための細工ではない。このデータセットだけが
 * 「候補プールに載っていない 1 件（バッジなし）+ 載っている 1 件（バッジあり）」を返し、
 * `SP-18` の「一部のカードにだけ Gem の印が付く」を実画面で写せる。他のキーワードが返すのは
 * すべて架空の `octostub/*` で、候補プール（`public/data/gem-index/`）に 1 件も載らないため
 * 印が 1 つも付かない（＝スライドで説明したい状態が撮れない）。
 */
test('shot-01: 検索結果一覧（Gem の印・Gem 一覧への導線）', async ({ page }, testInfo) => {
  await page.goto('/ja?q=gem-badge')
  // 一覧の最初のカードが描画されるまで待つ（レイアウト確定前に撮らない）。
  await page.getByRole('link', { name: 'octostub/not-a-gem' }).waitFor()
  // 印そのものが描かれるまで待つ（候補プールのシャード読み込みは初回だけ数秒かかる）。
  await page.getByText('（star の数のわりに、多くのパッケージから使われている候補です）').waitFor()
  await replaceStubAvatars(page)
  await page.screenshot({ path: `${OUT}/shot-01-${testInfo.project.name}.png` })
})

/**
 * スライド 3（Gem 一覧）用。検索語 `strftime` は `public/data/gem-index/` の実データから選んだ
 * （実測 6 件・レジストリが 4 種類に散り、先頭は「1,000 弱のパッケージから使われて star 7」という
 * Gem の定義そのものの例になる）。件数が少ないので **出典表記まで 1 枚に収まる**。
 *
 * 🔴 出典表記（`GR-6` / `D-29`）は一覧の末尾にあり、ファーストビューには入らないため
 * この 1 枚だけ `fullPage` で撮る（要件「出典表記が写っていること」を満たすため）。
 */
test('shot-03: Gem 一覧', async ({ page }, testInfo) => {
  await stubOwnerAvatars(page)
  await page.goto('/ja/gems?q=strftime')
  await page.getByRole('heading', { name: '「strftime」の Gem' }).waitFor({ timeout: 60_000 })
  // 出典表記（一覧末尾）が描かれてから撮る。
  await page.getByRole('link', { name: 'Ecosyste.ms' }).waitFor()
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${OUT}/shot-03-${testInfo.project.name}.png`, fullPage: true })
})

test('shot-02: 今日の Gem ダイジェスト', async ({ page }, testInfo) => {
  // `?date=` は `getDailyDigest` の並び替えシード。固定日付で再現性を担保する（ADR 0014 §2.2）。
  await page.goto('/ja?date=20260820')
  await page.getByRole('heading', { name: '今日の Gem', level: 2 }).waitFor()
  await replaceStubAvatars(page)
  // スマホ・PC とも **ファーストビューのまま** 撮る。共通ヘッダーとヒーロー画像
  // （`/images/hero-idle.webp`）は最初の画面にしか出ないため、スクロールすると資料から消える。
  // ヒーローが 16:9 になって縦幅が詰まった（#362）ので、スクロールしなくてもダイジェストが数件入る。
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${OUT}/shot-02-${testInfo.project.name}.png` })
})
