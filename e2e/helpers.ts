import type { Locator, Page } from '@playwright/test'

/**
 * 検索欄にキーワードを入力し、検索を実行する（SP-1 の操作レビュー手順 2. の共通化）。
 * `sp-1` / `sp-2` / `sp-3` / `a11y` の 4 ファイルで同じ 2 行が重複していたため切り出した
 * （`e2e/axe.ts` と同じ薄いヘルパーの置き方）。URL への反映やその後の検証は
 * 各 `test.step()` の意図が読めることを優先し、呼び出し側に委ねる（ここに `expect` は入れない）。
 */
export async function searchFor(page: Page, keyword: string): Promise<void> {
  await page.getByRole('searchbox', { name: '検索キーワード' }).fill(keyword)
  await page.getByRole('button', { name: '検索' }).click()
}

/**
 * `target` にフォーカスが乗るまで `Tab` を押し続ける（`SP-10` 操作レビュー手順 1.
 * キーボード完走のための共通化）。固定 Tab 回数の決め打ちは、中間に要素が 1 つ
 * 増減しただけで全テストが壊れるため避ける。
 *
 * 🔴 判定は `page.locator(':focus').and(target).count()`（`.count()` 版）を採る。
 * `target.evaluate((el) => el === document.activeElement)` 版は Playwright の
 * actionability 待機を内包するため、`target` のロケータが一度も要素にマッチしない
 * （ロール名の誤り等）場合に 1 回の呼び出しが外側のテストタイムアウト（60 秒）近くまで
 * ブロックし、下記の診断メッセージが一度も出ないまま Playwright の汎用タイムアウトで
 * 落ちる（原因が分かりにくい失敗になる）。`.count()` は actionability 待機を伴わない
 * 即時 DOM 照会なので、ロケータ誤りでも数秒で自前のエラーメッセージにより速く失敗する
 * （`content/discussions/sp10_a11y_20260820/whiteboard.md` round2 e2e_verify 自己批判・
 * round3 lead 判定 D-2 で確定）。
 */
export async function tabUntilFocused(page: Page, target: Locator, maxPresses = 40): Promise<void> {
  for (let i = 0; i < maxPresses; i++) {
    const focusedCount = await page.locator(':focus').and(target).count()
    if (focusedCount === 1) return
    await page.keyboard.press('Tab')
  }
  throw new Error(
    `Tab を ${maxPresses} 回押しても対象へフォーカスが到達しなかった（フォーカストラップまたはロケータの誤りの可能性）`,
  )
}
