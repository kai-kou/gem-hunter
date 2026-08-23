import { expect, test } from '@playwright/test'
import en from '../messages/en.json'
import ja from '../messages/ja.json'

/**
 * Issue #352: `app/[locale]/layout.tsx` の `export const metadata` が `description` を
 * 日本語リテラル固定で持っていたため、`/en` でも日本語の説明文が出力されていた
 * （実デプロイのレスポンスで確認済み）。`generateMetadata` へ切り替えてロケール別の
 * `messages.home.description` を返すようにした退行を検知する。
 */
test.describe('Issue #352: ルートメタデータの description がロケール別になる', () => {
  test('ja: /ja の <meta name="description"> が日本語の説明文である', async ({ page }) => {
    await page.goto('/ja')

    const description = page.locator('meta[name="description"]')
    await expect(description).toHaveCount(1)
    expect(await description.getAttribute('content')).toBe(ja.home.description)
  })

  test('en: /en の <meta name="description"> が英語の説明文である（日本語のままではない）', async ({
    page,
  }) => {
    await page.goto('/en')

    const description = page.locator('meta[name="description"]')
    await expect(description).toHaveCount(1)
    const content = await description.getAttribute('content')
    expect(content).toBe(en.home.description)
    expect(content).not.toBe(ja.home.description)
  })
})
