import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor, uniqueKeyword } from './helpers'

/**
 * `searchFor()`（`e2e/helpers.ts`）が「検索ナビゲーションの完了まで待ってから戻る」ことの
 * 回帰テスト（Issue #624 の同期是正・PR #841 Layer 1 指摘 F）。
 *
 * 🔴 なぜ要るか: この待ちが消えても、他の spec は呼び出し側の `expect(...).toBeVisible()`
 * （既定 5 秒）が待ちを肩代わりするため **全部緑のまま通ってしまう**（見えるのは負荷時の
 * フレークだけ）。待ちの有無そのものを観測する専用テストがなければ、将来の編集で
 * `waitForLoadState('domcontentloaded')` が落ちても誰も気づけない。
 *
 * 手口: スタブ（`e2e/stub/server.mjs`）の `sp9-slow` マーカーは検索応答を 1.5 秒遅らせる。
 * 待っていれば `searchFor()` の所要時間がその遅延を含み、戻った直後には結果が描画済みになる。
 * 待っていなければ 100ms 前後で戻り、結果はまだ届いていない（下の 2 つの assert が両方落ちる）。
 */

/** `e2e/stub/server.mjs` の `SP9_SLOW_DELAY_MS`（遅延応答の長さ）。 */
const SP9_SLOW_DELAY_MS = 1_500

/**
 * 所要時間の下限。計測は `Date.now()` の差分（ヘルパー呼び出しの前後）なので、
 * 遅延そのものより数十 ms 短く出る余地を見込んで少しだけ緩める。待ちが消えたときの実測は
 * 71〜301ms なので、この下限でも決定論的に落ちる。
 */
const MIN_ELAPSED_MS = 1_200

/**
 * 「戻った時点で描画済み」を判定するための assertion 予算。既定（5 秒）のままだと
 * 待ちが消えていても assertion 側が待ってしまい、このテストが何も担保しなくなる。
 *
 * 🔴 **250ms だった値は Issue #978 で不安定と判明し、根拠つきで 500ms へ引き上げた
 * （予算の緩和で誤魔化しているのではない・直接原因を実測で特定済み）**。
 *
 * 直接原因: `waitForLoadState('domcontentloaded')` は正しく機能しており、HTML 本文
 * （Suspense の解決済みコンテンツを含む）は domcontentloaded の時点で **常に既にレスポンス
 * 本文へ到達している**。しかし本アプリの `app/[locale]/page.tsx` は `statePromise` を
 * 2 つの独立した `<Suspense>`（`SearchStatusText` = B:0 / `SearchBody` = B:1・ライブ
 * リージョンと本体を分ける a11y 上の理由がある。同ファイルの JSDoc 参照）で待つ構成で、
 * 同じ Promise から 2 つの境界がほぼ同時に解決する。
 *
 * React（`react-dom/server` の Fizz ストリーミング）はクライアント側に埋め込む
 * `$RC`/`$RB`/`$RV`/`$RT` という境界解放（reveal）用インラインスクリプトを生成する。
 * 実測した失敗時の HTML（`$RC("B:0","S:0")` → 直後に `$RC("B:1","S:1")`）を見ると、
 * 1 つ目の境界は最初の `requestAnimationFrame` で即座に反映されるが、2 つ目の境界は
 * 「`$RT`（1 フレーム目のタイムスタンプ）が既に number 化されている」場合に
 * `setTimeout(..., $RT + 300 - performance.now())` という **React 自身が持つハードコード
 * 300ms のバッチ化タイマー**（複数の境界解決を 1 回のペイント・レイアウトへまとめるための
 * React 内部の意図的な設計）で遅延反映される。応答が速いほど `performance.now()` が
 * `$RT` に近く、遅延がほぼ 300ms 丸ごと乗る。応答が遅い（`sp9-slow` の 1.5 秒）場合は
 * domcontentloaded の時点で既に `$RT + 300` を過ぎているため、この遅延は事実上ゼロになる
 * （フェイル側が「高速応答」のテストだけに現れ、「低速応答」のテストは安定していた理由）。
 *
 * この遅延は `searchFor()` のヘルパー実装や本テストの待ち方の誤りではなく、React の
 * ストリーミング SSR ランタイムが正規に持つスケジューリング（本アプリの入力ではコード側で
 * 回避できない）。実測（ローカル・80 回試行）では失敗時の追加待ち時間は 295〜301ms
 * だったため、300ms 理論上限 + ブラウザのスケジューリング揺らぎの安全マージンとして
 * 500ms を採用した（`waitForResponse` 既定 30 秒のような「実質無制限」への後退ではなく、
 * 実測された固有の遅延要因に対する最小限の引き上げ）。
 */
const ALREADY_RENDERED_BUDGET_MS = 500

test.describe('E2E ヘルパー: searchFor は検索ナビゲーションの完了まで待つ', () => {
  test('応答が 1.5 秒遅い検索でも、戻った時点で結果が描画済みである（Issue #624）', async ({
    page,
  }) => {
    await page.goto('/ja')

    const startedAt = Date.now()
    await searchFor(page, uniqueKeyword('sp9-slow'))
    const elapsedMs = Date.now() - startedAt

    await test.step('1. ヘルパーが上流の遅延を含めて待っている', async () => {
      expect(
        elapsedMs,
        `searchFor() が ${SP9_SLOW_DELAY_MS}ms 遅い応答を待たずに戻った（実測 ${elapsedMs}ms）`,
      ).toBeGreaterThanOrEqual(MIN_ELAPSED_MS)
    })

    await test.step('2. 戻った時点で結果 HTML が到達している（読み込み中でも空でもない）', async () => {
      await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible({
        timeout: ALREADY_RENDERED_BUDGET_MS,
      })
      await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
    })
  })

  /**
   * 干渉検証（複数対策の相互作用）: 本 PR は同じ `searchFor()` の中に
   * ① 待ち受け登録と `click()` の `Promise.all` 化 ② 3xx を除外する状態コード判定
   * ③ `SEARCH_PARAM_KEYS` への一本化、という独立した対策を同居させている。
   * ①〜③ は同じ入力（キーワード）と同じ応答オブジェクトを順に通るため、
   * どれか 1 つが他の前提を壊すと **応答待ちが永久に一致せず** 30 秒でタイムアウトする。
   *
   * 上の遅い応答（1.5 秒）だけでは「登録が click に間に合っているか」（①）は分からない
   * （遅延のおかげで後から登録しても間に合ってしまう）。応答が数十 ms で返る通常の
   * キーワードで、待ち受けの取りこぼしも述語の不一致も起きないことをここで確認する。
   */
  test('高速応答の検索でも待ち受けを取りこぼさず、戻った時点で結果が描画済みである', async ({
    page,
  }) => {
    await page.goto('/ja')

    // `sp9-slow` などのマーカーを含まない通常のキーワード（スタブは即座に 1 ページ目を返す）。
    await searchFor(page, uniqueKeyword('fast-response'))

    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible({
      timeout: ALREADY_RENDERED_BUDGET_MS,
    })
    await expect(page.locator('main').getByText(ja.common.loading)).toHaveCount(0)
  })
})
