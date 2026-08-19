import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * SP-5: 同じ検索・同じ詳細で GitHub API を二度叩かない。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-5` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応 `NFR`: `NFR-5` / `NFR-17` / `NFR-18`。
 *
 * 🔵 検証方式（議論で確定済み）: 本来の確認手段の正本はレスポンスヘッダ `X-Cache-Status`
 * （`cloudflare-infrastructure.md` §4.5）だが、それは Cloudflare Workers 上の自前エントリ
 * （`worker-entry.ts`）が付与するもので、この E2E が使う `playwright.config.ts` の `webServer`
 * （`next build && next start` = Node.js）では出ない。そのため本ファイルの主 assert は
 * **「スタブ GitHub API への実リクエスト数が 2 回目で増えないこと」**（`e2e/stub/server.mjs`
 * の `/__stats`）にする。ヘッダの確認はプレビュー環境（Workers）での手動 curl に委ねる
 * （手順は PR 本文）。
 *
 * キャッシュはプロセス（isolate）内で共有される単一インスタンス
 * （`src/composition/container.ts` の `sharedCache`）のため、他の E2E ファイルが既に検索・
 * 参照したキーワード / リポジトリを使うと「1 回目」のはずが既にキャッシュ済みで
 * スタブへ届かない（テスト間の残留状態に依存してしまう）。そのためここでは他ファイルが
 * 使わないキーワード（`sp5-cache-check`）と、詳細を未訪問のリポジトリ（`octo-forms`。
 * `sp-3` は `octo-widgets` を使う）を選んで独立させる。
 */

const STUB_ORIGIN = `http://127.0.0.1:${process.env.E2E_STUB_PORT ?? '8788'}`

type StubStats = { searchCount: number; detailCount: number }

/** スタブへ実際に届いたリクエスト数を読む（`e2e/stub/server.mjs` の `/__stats`）。 */
async function readStubStats(): Promise<StubStats> {
  const res = await fetch(`${STUB_ORIGIN}/__stats`)
  return (await res.json()) as StubStats
}

/** スタブのリクエストカウントを 0 に戻す（他テストの残留カウントを引き継がない）。 */
async function resetStubStats(): Promise<void> {
  await fetch(`${STUB_ORIGIN}/__stats/reset`, { method: 'POST' })
}

test('SP-5: 同じ検索・同じ詳細で GitHub API を二度叩かない', async ({ page }) => {
  await test.step('前提: スタブのリクエストカウントをリセットする', async () => {
    await resetStubStats()
    const stats = await readStubStats()
    expect(stats.searchCount).toBe(0)
    expect(stats.detailCount).toBe(0)
  })

  await test.step('1. 検索する（1 回目）→ スタブへ検索リクエストが 1 回届く', async () => {
    await page.goto('/ja')
    await searchFor(page, 'sp5-cache-check')
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.searchCount).toBe(1)
  })

  await test.step('2. 同じキーワードで続けてもう一度検索する（2 回目）→ スタブへのリクエスト数は増えない', async () => {
    await searchFor(page, 'sp5-cache-check')
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.searchCount).toBe(1)
  })

  let detailUrl = ''

  await test.step('3. 詳細ページを開く（1 回目）→ スタブへ詳細リクエストが 1 回届く', async () => {
    await page.getByRole('link', { name: 'octostub/octo-forms' }).click()
    await expect(page.getByRole('heading', { name: 'octostub/octo-forms' })).toBeVisible()
    detailUrl = page.url()

    const stats = await readStubStats()
    expect(stats.detailCount).toBe(1)
  })

  await test.step('4. 同じ詳細ページを再訪問する（2 回目）→ 外部リクエストなしで表示される', async () => {
    await page.goto(detailUrl)
    await expect(page.getByRole('heading', { name: 'octostub/octo-forms' })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.detailCount).toBe(1)
  })
})

/**
 * SP-5 フォールバック経路: `X-Cache-Status` ヘッダの観測（`app/api/search/route.ts`）。
 *
 * 画面の SSR 応答には `X-Cache-Status` を載せられない（`AsyncLocalStorage` 案が実機検証で
 * 不成立・whiteboard round 3 lead 裁定）ため、この Route Handler がヘッダ観測の唯一の経路になる。
 * 上のテストと同じキャッシュ（`sharedCache`）をプロセス内で共有するため、他ファイルは
 * もちろん上のテストとも被らない未使用キーワード（`sp5-route-header-check`）を使う。
 */
test('SP-5: /api/search が X-Cache-Status ヘッダで HIT/MISS を報告する', async ({ request }) => {
  const params = { q: 'sp5-route-header-check', page: '1' }

  const first = await request.get('/api/search', { params })
  expect(first.ok()).toBe(true)
  expect(first.headers()['x-cache-status']).toBe('MISS')

  const second = await request.get('/api/search', { params })
  expect(second.ok()).toBe(true)
  expect(second.headers()['x-cache-status']).toBe('HIT')
})
