import type { Page } from '@playwright/test'

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
