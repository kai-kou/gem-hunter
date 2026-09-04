import { expect, test } from '@playwright/test'
import type { Locator, Page, Route } from '@playwright/test'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'
import { uniqueKeyword } from './helpers'

/**
 * Issue #167「詳細ページの読み込み中表示を、404 の HTTP ステータスを保ったまま実現する」の E2E。
 * 対応: `US-22`（読み込み中が伝わる）/ `AC-5`（存在しない詳細は 404 を返す）/ `AC-8`（読み込み中を判別できる）/
 * `NFR-12`（視覚表現だけにしない）。
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
 *   - 支援技術向けの通知は **一覧ごとに 1 個だけ常設** した `data-testid="link-pending-announcer"`
 *     （`role="status"` / `aria-live="polite"` / `sr-only`）が一手に担う。リンクごとに
 *     ライブリージョンを増やさない（`ui-ux-guidelines.md` §7.2）
 *
 * 🔴 #349 の規律: 「属性が付いているか」で終わらせず、`getComputedStyle` の **計算後の値**
 * （`opacity`）まで実測する。クラスは付くが CSS が当たっていない状態を素通りさせないため。
 */

/**
 * 詳細ページへのナビゲーションを意図的に遅らせる幅（ms）。
 *
 * 🔴 **Playwright の `expect` 既定タイムアウト（5,000ms）より明確に長い値にする**
 * （`playwright.config.ts` に `expect.timeout` の上書きは無い。同 config の `timeout: 60_000` は
 * **test** timeout であって expect ではない）。5,000ms と同値だと「観測窓 = アサーション予算」に
 * なって余裕がゼロになり、遅延明けに `data-pending` が `false` へ戻って hint が detach した
 * 瞬間に観測側が例外で落ちる（しかも原因が『opacity が 1 でない』に見える）。
 * 8,000ms なら、下の `PENDING_OBSERVATION_TIMEOUT_MS`（4,000ms）で観測を終えてもなお
 * 4,000ms の余白が残る。
 */
const NAVIGATION_DELAY_MS = 8_000

/** ペンディング表示（属性・計算後スタイル・読み上げ文言）の観測に与える予算。`NAVIGATION_DELAY_MS` の半分。 */
const PENDING_OBSERVATION_TIMEOUT_MS = 4_000

/** 遅延明けの遷移完了を待つ予算（遅延 8s + 詳細ページの RSC レンダーを十分に含む）。 */
const NAVIGATION_SETTLE_TIMEOUT_MS = 30_000

/**
 * 支援技術へ読み上げられる文言（ja）。
 * 🔴 実装側の定数・`messages/ja.json` を参照せず **リテラルで書く**（`testing-strategy.md` §7:
 * 実装から import した値を期待値にすると、実装を巻き戻しても一致し続けて退行検知力がゼロになる）。
 */
const PENDING_ANNOUNCEMENT_JA = '詳細ページを読み込んでいます'

/** 一覧ページ内の「詳細リンク」（`/{locale}/repos/{owner}/{repo}` を指す `<a>`）。 */
function detailLinks(page: Page): Locator {
  return page.locator('main ul li a[href*="/repos/"]')
}

/** 詳細リンクの内側に常設されるペンディングヒント（`link` スコープ限定）。 */
function pendingHintOf(link: Locator): Locator {
  return link.locator('[data-testid="link-pending-hint"]')
}

/** 一覧ごとに 1 個だけ常設される、支援技術向けライブリージョン。 */
function pendingAnnouncer(page: Page): Locator {
  return page.getByTestId('link-pending-announcer')
}

type RouteStats = {
  /** `next-router-prefetch: 1` として観測し 204 で握った件数（この分岐が生きているかの証跡）。 */
  prefetch: number
  /** 実際に遅延させた本番ナビゲーション（document / RSC）の件数。 */
  delayed: number
}

/**
 * 詳細ページの document / RSC リクエストを遅延させる。
 *
 * 🔴 **`page.goto()` より前に登録すること**（この関数の呼び出し順序が要件）。`<Link>` の
 * viewport prefetch はページ表示直後に飛ぶため、`goto` の後に登録するとキャッシュ済みの
 * prefetch を抑止できず、セーフガードが fail-open で無効化される。
 *
 * 🔴 prefetch は `route.abort()` ではなく **204 で正常終了させる**。abort するとルーター
 * キャッシュにエラーとして残り、続くクリックがハードナビゲーションへ倒れうる（そうなると
 * `useLinkStatus` のペンディングが観測できない）。204 なら「中身の無い prefetch」として
 * 素直に扱われ、クリック時に本番の取得が改めて走る（＝この遅延の対象になる）。
 *
 * 🔴 分岐の到達件数を数えて返す。`next-router-prefetch` は Next.js の内部ヘッダ名なので、
 * 名前が変わればこのセーフガードは黙って無効化される。呼び出し側が件数を検証・記録する。
 */
async function installDetailNavigationDelay(page: Page): Promise<RouteStats> {
  const stats: RouteStats = { prefetch: 0, delayed: 0 }

  await page.route('**/repos/**', async (route: Route) => {
    if (route.request().headers()['next-router-prefetch'] === '1') {
      stats.prefetch += 1
      await route.fulfill({ status: 204, body: '' })
      return
    }
    stats.delayed += 1
    await new Promise((resolve) => setTimeout(resolve, NAVIGATION_DELAY_MS))
    await route.continue()
  })

  return stats
}

/** 検索 URL を組み立てる（パラメータ名は `SEARCH_PARAM_KEYS` が正本・直書きしない）。 */
function searchUrl(keyword: string): string {
  return `/ja?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(keyword)}`
}

test.describe('Issue #167: 一覧 → 詳細の遷移中にペンディング表示が出る', () => {
  // beforeEach が落ちたときも afterEach が二次エラーで原因を覆い隠さないよう既定値を持たせる。
  let routeStats: RouteStats = { prefetch: 0, delayed: 0 }

  test.beforeEach(async ({ page }) => {
    // 🔴 route → goto の順序が本 spec の前提（上記 JSDoc）。初期化を 1 か所に括ることで
    // 「テストによっては goto が先」という取りこぼしを構造的に防ぐ。
    routeStats = await installDetailNavigationDelay(page)
  })

  test.afterEach(() => {
    // 黙って劣化させないための証跡（ヘッダ名が変わって prefetch 分岐に一度も入らなくなった等）。
    test.info().annotations.push({
      type: 'route-guard',
      description: `prefetch=${routeStats.prefetch} delayed=${routeStats.delayed}`,
    })
  })

  test('初期状態: ヒントは各リンクに常設・opacity 0、ライブリージョンは一覧に 1 個だけで空（レイアウトシフト防止 / §7.2）', async ({
    page,
  }) => {
    // 🔴 20 件データセットを使う: 「ライブリージョンがリンク数に比例して増えていない」ことは
    //    リンクが 3 件では弱い証拠にしかならない（`many-hits` は 1 ページ 20 件・`e2e/stub/server.mjs`）。
    const keyword = uniqueKeyword('many-hits')
    let linkCount = 0

    await test.step('1. 一覧を表示する', async () => {
      await page.goto(searchUrl(keyword))
      await expect(detailLinks(page).first()).toBeVisible()
      linkCount = await detailLinks(page).count()
      // 「対象 0 件でも成立する不変条件」を置かない（`testing-strategy.md` §7）ため、
      // まず対象が十分な数あることを固定する。
      expect(linkCount, '詳細リンクが 2 件以上描画されていること').toBeGreaterThan(1)
    })

    await test.step('2. 各詳細リンクの内側にヒントが 1 つずつ常設されている', async () => {
      // 🔴 スコープを揃えて等値比較する（ページ全体の件数と一覧内の件数を突き合わせない）。
      await expect(detailLinks(page).locator('[data-testid="link-pending-hint"]')).toHaveCount(
        linkCount,
      )
      const hints = pendingHintOf(detailLinks(page).first())
      await expect(hints).toHaveCount(1)
      await expect(hints).toHaveAttribute('data-pending', 'false')
      await expect(hints).toHaveAttribute('aria-hidden', 'true')
    })

    await test.step('3. 非ペンディング時の計算後スタイルは opacity 0（かつ display は none でない）', async () => {
      const hint = pendingHintOf(detailLinks(page).first())
      // 🔴 一発の `evaluate` ではなく `expect.poll` で読む。`toBeVisible()` はスタイルシートの
      //    適用完了までは保証しないため、CSS が当たる前に読むと「opacity が既定値の 1」を
      //    掴んで偽陽性で落ちる（実測でフレークを確認）。
      await expect
        .poll(() => hint.evaluate((el) => Number(getComputedStyle(el).opacity)), {
          message: '非ペンディング時の hint は計算後 opacity が 0 であること',
        })
        .toBe(0)
      // display:none にすると寸法が消えてペンディング時にレイアウトシフトする（契約違反）
      const display = await hint.evaluate((el) => getComputedStyle(el).display)
      expect(display).not.toBe('none')
    })

    await test.step('4. ライブリージョンは一覧に 1 個だけ常設され、初期状態では空（US-22 / NFR-12）', async () => {
      const announcer = pendingAnnouncer(page)
      await expect(announcer).toHaveCount(1)
      await expect(announcer).toHaveAttribute('role', 'status')
      await expect(announcer).toHaveAttribute('aria-live', 'polite')
      await expect(announcer).toHaveClass(/\bsr-only\b/)
      await expect(announcer).toBeEmpty()
    })

    await test.step('5. リンクごとにライブリージョンを増やしていない（リンク数に比例しない・回帰）', async () => {
      // 一覧項目の内側にライブリージョンが 1 つも無いこと（= リンク数だけ増える実装への退行検知）。
      await expect(page.locator('main ul li [role="status"]')).toHaveCount(0)
      // ページ全体でも、リンク数（20）に比例した数にはならない。
      const statusCount = await page.locator('[role="status"]').count()
      expect(
        statusCount,
        `role="status" の総数がリンク数（${linkCount}）に比例していないこと`,
      ).toBeLessThan(linkCount)
    })
  })

  test('クリック中: ヒントが data-pending="true" / opacity 1 になり、常設ライブリージョンが読み上げ文言を持つ（US-22 / AC-8 / AC-5）', async ({
    page,
  }) => {
    const keyword = uniqueKeyword('link-pending')
    const link = detailLinks(page).first()
    const hint = pendingHintOf(link)
    const announcer = pendingAnnouncer(page)
    let expectedHref = ''
    let expectedName = ''

    await test.step('1. 一覧を表示する（詳細への遷移は beforeEach で遅延済み）', async () => {
      await page.goto(searchUrl(keyword))
      await expect(link).toBeVisible()
      expectedHref = (await link.getAttribute('href')) ?? ''
      expectedName = (await link.innerText()).trim()
      expect(expectedHref, '詳細リンクの href が取れていること').toContain('/repos/')

      // 遷移前のライブリージョンは空。ここで DOM ノードに印を付け、遷移中に
      // **同じノードの中身だけが書き換わる**（要素ごと差し替えていない）ことを次のステップで確かめる。
      await expect(announcer).toBeEmpty()
      await announcer.evaluate((el) => el.setAttribute('data-e2e-identity', 'before-click'))
    })

    await test.step('2. クリック直後、そのリンクのヒントがペンディングになる', async () => {
      await link.click()
      await expect(hint).toHaveAttribute('data-pending', 'true', {
        timeout: PENDING_OBSERVATION_TIMEOUT_MS,
      })
    })

    await test.step('3. 🔴 #349: 計算後の opacity が実際に 1 相当へ変わっている', async () => {
      // 🔴 `.catch()` で握り潰さない。遅延明けに hint が detach したなら、その例外
      //    （＝観測窓を取り違えている）をそのまま失敗として見せる。
      await expect
        .poll(() => hint.evaluate((el) => Number(getComputedStyle(el).opacity)), {
          message: 'ペンディング中の hint は計算後 opacity が 1 相当であること',
          timeout: PENDING_OBSERVATION_TIMEOUT_MS,
        })
        .toBeGreaterThan(0.9)
    })

    await test.step('4. 常設ライブリージョンに読み上げ文言が入る（要素は差し替えられていない）', async () => {
      await expect(announcer).toHaveText(PENDING_ANNOUNCEMENT_JA, {
        timeout: PENDING_OBSERVATION_TIMEOUT_MS,
      })
      // 同じ DOM ノードのままであること（`ui-ux-guidelines.md` §7.2: 要素ごと動的挿入しない）。
      await expect(announcer).toHaveCount(1)
      await expect(announcer).toHaveAttribute('data-e2e-identity', 'before-click')
    })

    await test.step('5. 遅延が明けると詳細ページが表示される（404 にならない・回帰）', async () => {
      await expect(page).toHaveURL(expectedHref, { timeout: NAVIGATION_SETTLE_TIMEOUT_MS })
      await expect(page.getByRole('heading', { level: 2, name: expectedName })).toBeVisible({
        timeout: NAVIGATION_SETTLE_TIMEOUT_MS,
      })
    })

    await test.step('6. prefetch 抑止の分岐が実際に発火していた（安全網が黙って無効化されていないこと）', () => {
      // Next.js 内部ヘッダ名（`next-router-prefetch`）が変わると、この分岐は静かに死ぬ。
      // 件数を明示的に検証して「効いているつもり」を残さない。
      expect(routeStats.prefetch, 'prefetch を 204 で握った件数').toBeGreaterThan(0)
      expect(routeStats.delayed, '遅延させた本番ナビゲーションの件数').toBeGreaterThan(0)
    })
  })
})
