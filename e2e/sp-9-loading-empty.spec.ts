import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * SP-9 操作レビュー手順 1.「該当のないキーワードで検索 → 0 件が明示される（読み込み中との区別がつく）」
 * （`docs/02_requirements/user-story-map.md` §5.3 `SP-9`・対応 `AC-8` / `US-22` / `US-23`）。
 *
 * 「読み込み中」と「0 件」は **別の要素・別の文言** で出す（同じ空欄に見えない）ことが要件なので、
 * 片方が出ているときにもう片方が出ていないことまで検証する。
 *
 * 読み込み中は一瞬で終わってしまうと観測できないため、スタブ（`e2e/stub/server.mjs`）の
 * `sp9-slow` マーカーで応答を 1.5 秒遅らせ、`waitUntil: 'commit'` でストリーミングの
 * 先頭（`<Suspense>` の fallback）を捕まえる。
 */

/**
 * 実行のたびに一意なキーワードを作る（`sp-5.spec.ts` / `ac-12-private.spec.ts` と同じ手口）。
 * キャッシュ（プロセス内共有・TTL あり）に前回試行の結果が残っていると、スタブの遅延分岐や
 * 0 件分岐まで到達せず観測できないため、構造的にキャッシュミスにする。
 */
function uniqueKeyword(prefix: string): string {
  return `${prefix}-${randomBytes(4).toString('hex')}`
}

test.describe('SP-9: 読み込み中と 0 件が区別できる', () => {
  test('読み込み中は role="status" の「読み込み中」で伝わり、結果が届くと消える（US-22）', async ({
    page,
  }) => {
    const keyword = uniqueKeyword('sp9-slow')

    await test.step('1. 応答が遅い検索を開き、ストリーミングの先頭を捕まえる', async () => {
      await page.goto(`/ja?q=${keyword}`, { waitUntil: 'commit' })
      const status = page.locator('main').getByRole('status')
      await expect(status).toContainText(ja.common.loading)
      await expect(status).toHaveAttribute('aria-live', 'polite')
    })

    await test.step('2. 見出しと検索欄は待ち時間中も表示されている（LCP 要素を隠さない）', async () => {
      await expect(page.getByRole('heading', { name: ja.home.title })).toBeVisible()
      await expect(page.getByRole('searchbox', { name: ja.home.searchLabel })).toBeVisible()
    })

    await test.step('3. 結果が届くと読み込み中表示が消える', async () => {
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
    })
  })

  /**
   * 🔴 クライアント遷移（`next/link` によるページング・ソート変更・表示件数変更）でも
   * 読み込み中が出ることの回帰テスト（SP-9 セルフレビュー指摘 2）。
   *
   * React は transition 中に **既存の** `<Suspense>` 境界の fallback を再表示しないため、
   * `key` が無いと「古い一覧が残ったまま無反応」に見える（`US-22` の主要導線が未達になる）。
   * `page.goto()` のハード遷移では境界が毎回作り直されるので検知できない。
   */
  test('ページングのクライアント遷移でも読み込み中が出る（US-22）', async ({ page }) => {
    const keyword = uniqueKeyword('sp9-slow')

    await test.step('1. 応答が遅い検索の結果を表示しておく', async () => {
      await page.goto(`/ja?q=${keyword}`)
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
    })

    await test.step('2. 次のページへのリンク（クライアント遷移）を押すと読み込み中が出る', async () => {
      await page.getByRole('link', { name: ja.home.pageNext }).click()
      await expect(page.locator('main').getByRole('status')).toContainText(ja.common.loading)
    })

    await test.step('3. 2 ページ目の結果が届くと読み込み中は消える', async () => {
      await expect(page).toHaveURL(/page=2/)
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
    })
  })

  test('0 件は該当なしの文言を role="status" で明示する（US-23 / US-26）', async ({ page }) => {
    await test.step('1. 該当のないキーワードで検索する', async () => {
      await page.goto('/ja')
      await searchFor(page, uniqueKeyword('zero-hits'))
    })

    await test.step('2. 0 件であることが明示され、読み込み中・エラーとは別物として出ている', async () => {
      // 🔴 #180 是正（section へ role="status" 追加）後は main 内に role="status" が 2 つ存在する
      // （① #search-status セクション＝件数文言「0 件中 0 件を表示」 ② RepositoryList の 0 件専用
      // <p role="status">）。単純な getByRole('status') は strict mode violation で必ず落ちるため、
      // 文言で対象を絞り込む（whiteboard round2 e2e_verify rebuttal・実機再現で確定）。
      const status = page.locator('main').getByRole('status').filter({ hasText: ja.home.empty })
      await expect(status).toContainText(ja.home.empty)
      // 読み込み中（US-22）と 0 件（US-23）を同じ表示にしない（AC-8）
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
      // 0 件はエラーではない（role="alert" にしない・ui-ux-guidelines.md §7.2）
      await expect(page.locator('main').getByRole('alert')).toHaveCount(0)
      // Issue #347 T-5: 0 件の装飾画像（alt=""）が main 内に可視で存在すること。
      await expect(page.locator('main img[alt=""]')).toBeVisible()
      // 🔴 構造契約: role="status" の要素の中に img が無いこと（a11y_i18n round3・
      // repository-list.tsx の確定マークアップ「画像は status 要素の外＝兄弟」の回帰防止）。
      await expect(status.locator('img')).toHaveCount(0)
    })

    await test.step('3. 検索欄は残り、別のキーワードへ直せる', async () => {
      await expect(page.getByRole('searchbox', { name: ja.home.searchLabel })).toBeEditable()
    })
  })
})

/**
 * スタブサーバー自身の堅牢性（SP-9 セルフレビュー指摘 8）。
 * 遅延応答（`sp9-slow`）の `setTimeout` が `res` の生存を確認せずに書き込むと、テスト中断や
 * ナビゲーション破棄でソケットが閉じた後に `ERR_STREAM_WRITE_AFTER_END` でスタブプロセスが
 * 落ち、後続の spec が全滅する。切断後もスタブが応答し続けることを直接確認する。
 */
test('スタブは遅延応答中にクライアントが切断しても落ちない（E2E 基盤の堅牢性）', async () => {
  const stubOrigin = `http://127.0.0.1:${process.env.E2E_STUB_PORT ?? '8788'}`
  const controller = new AbortController()

  const pending = fetch(`${stubOrigin}/search/repositories?q=${uniqueKeyword('sp9-slow')}&page=1`, {
    signal: controller.signal,
  }).catch(() => undefined)
  // 応答が返る前（遅延 1.5 秒）に切断する
  await new Promise((resolve) => setTimeout(resolve, 200))
  controller.abort()
  await pending

  // 遅延タイマーが発火し終わるまで待ってから、スタブがまだ生きていることを確認する
  await new Promise((resolve) => setTimeout(resolve, 2_000))
  const stats = await fetch(`${stubOrigin}/__stats`)
  expect(stats.ok, 'スタブプロセスが生存していること').toBe(true)
})
