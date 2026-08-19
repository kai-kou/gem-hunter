import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * SP-5: 同じ検索・同じ詳細で GitHub API を二度叩かない。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-5` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応 `NFR`: `NFR-5` / `NFR-17` / `NFR-18`。
 *
 * 🔵 検証方式（議論で確定済み）: 本来の確認手段の正本はレスポンスヘッダ `X-Cache-Status`
 * （`app/api/search/route.ts` の Route Handler が付与する）だが、画面
 * （`app/[locale]/page.tsx`）の SSR 応答にはこのヘッダを載せられない（`AsyncLocalStorage` 案が
 * 実機検証で不成立・whiteboard round 3 lead 裁定。ヘッダを付与していた `worker-entry.ts` は
 * SP-5 の過程で削除済み）。そのため画面操作を確認する主 assert は **「スタブ GitHub API への
 * 実リクエスト数が 2 回目で増えないこと」**（`e2e/stub/server.mjs` の `/__stats`）にする。
 * ヘッダそのものの確認は本ファイル下部の `/api/search` 直叩きテストが担う（Route Handler は
 * Node の `next start` でも動くため、ローカル E2E でもヘッダを観測できる）。
 *
 * キャッシュはプロセス（isolate）内で共有される単一インスタンス
 * （`src/composition/container.ts` の `sharedCache`）で、`playwright.config.ts` は
 * `fullyParallel: false` / `workers: 1` のため、実行中の全 E2E ファイル・**同一テストの
 * retry 試行** が同じキャッシュ・同じ `webServer` プロセスを共有する。固定のキーワード /
 * 固定のリポジトリを使うと、他ファイルや前回の retry 試行が既に問い合わせ済みで「1 回目のはず」
 * が実は HIT になり、retry が本来の一時障害検知を隠してしまう（実機で `--retries=1` にして
 * 再現確認済み）。検索キーワードは実行のたびに一意な値を生成して構造的にこれを避け（下記
 * `uniqueKeyword`）、詳細ページのリポジトリは動的生成できない（スタブが固定 5 件のフィクスチャ
 * しか持たない）ため、retry 試行ごとに他ファイルが使わない予備リポジトリへ切り替える（下記
 * `DETAIL_REPO_POOL`）。
 */

const STUB_ORIGIN = `http://127.0.0.1:${process.env.E2E_STUB_PORT ?? '8788'}`

type StubStats = { searchCount: number; detailCount: number }

/**
 * 実行のたびに一意な検索キーワードを生成する（他ファイル・retry 試行との衝突をコードで防ぐ。
 * 「他ファイルとキーワードが被らないよう気をつける」という人間の注意力に頼らない）。
 * スタブ（`e2e/stub/server.mjs`）は `q` を `zero-hits` / `upstream-error` / `rate-limit` の
 * 特殊部分一致でのみ分岐させ、それ以外は内容を見ずに固定フィクスチャを返す。16 進数だけの
 * 接尾辞（上記いずれの単語とも一致し得ない）を付ければ安全に一意化できる。
 */
function uniqueKeyword(base: string): string {
  return `${base}-${randomBytes(4).toString('hex')}`
}

/**
 * 詳細ページ用の予備リポジトリ（フィクスチャ 5 件のうち、他の E2E ファイルが detail 遷移で
 * 使わないもの。`octo-widgets` は `sp-3` / `a11y` が detail 遷移に使用済みのため対象外）。
 * retry のたびに切り替えることで、前回試行のキャッシュ（TTL 300 秒）に当たらないようにする。
 * `playwright.config.ts` は `CI` 時のみ `retries: 1`（最大 2 試行）なので 2 件で足りる。
 */
const DETAIL_REPO_POOL = ['octo-forms', 'octo-charts'] as const

function detailRepoForAttempt(retry: number): string {
  return DETAIL_REPO_POOL[retry % DETAIL_REPO_POOL.length]
}

/**
 * スタブへ実際に届いたリクエスト数を読む（`e2e/stub/server.mjs` の `/__stats`）。
 * 応答が失敗した場合は「アサーションの値が食い違う」という遠回しな失敗ではなく、
 * スタブ未起動が原因だと即座に分かるメッセージで落とす。
 */
async function readStubStats(): Promise<StubStats> {
  const res = await fetch(`${STUB_ORIGIN}/__stats`)
  if (!res.ok) {
    throw new Error(`stub の /__stats が応答しない（status=${res.status}）。E2E スタブサーバー（e2e/stub/server.mjs）が起動しているか確認してほしい`)
  }
  return (await res.json()) as StubStats
}

/** スタブのリクエストカウントを 0 に戻す（他テスト・前回 retry 試行の残留カウントを引き継がない）。 */
async function resetStubStats(): Promise<void> {
  const res = await fetch(`${STUB_ORIGIN}/__stats/reset`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`stub の /__stats/reset が応答しない（status=${res.status}）。E2E スタブサーバー（e2e/stub/server.mjs）が起動しているか確認してほしい`)
  }
}

test('SP-5: 同じ検索・同じ詳細で GitHub API を二度叩かない', async ({ page }, testInfo) => {
  const keyword = uniqueKeyword('sp5-cache-check')
  const detailRepoName = detailRepoForAttempt(testInfo.retry)
  const detailFullName = `octostub/${detailRepoName}`

  await test.step('前提: スタブのリクエストカウントをリセットする', async () => {
    await resetStubStats()
    const stats = await readStubStats()
    expect(stats.searchCount).toBe(0)
    expect(stats.detailCount).toBe(0)
  })

  await test.step('1. 検索する（1 回目）→ スタブへ検索リクエストが 1 回届く', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.searchCount).toBe(1)
  })

  await test.step('2. 同じキーワードで続けてもう一度検索する（2 回目）→ スタブへのリクエスト数は増えない', async () => {
    await searchFor(page, keyword)
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.searchCount).toBe(1)
  })

  let detailUrl = ''

  await test.step('3. 詳細ページを開く（1 回目）→ スタブへ詳細リクエストが 1 回届く', async () => {
    await page.getByRole('link', { name: detailFullName }).click()
    await expect(page.getByRole('heading', { name: detailFullName })).toBeVisible()
    detailUrl = page.url()

    const stats = await readStubStats()
    expect(stats.detailCount).toBe(1)
  })

  await test.step('4. 同じ詳細ページを再訪問する（2 回目）→ 外部リクエストなしで表示される', async () => {
    await page.goto(detailUrl)
    await expect(page.getByRole('heading', { name: detailFullName })).toBeVisible()

    const stats = await readStubStats()
    expect(stats.detailCount).toBe(1)
  })
})

/**
 * SP-5 フォールバック経路: `X-Cache-Status` ヘッダの観測（`app/api/search/route.ts`）。
 *
 * 画面の SSR 応答には `X-Cache-Status` を載せられない（`AsyncLocalStorage` 案が実機検証で
 * 不成立・whiteboard round 3 lead 裁定）ため、この Route Handler がヘッダ観測の唯一の経路になる。
 * ヘッダの値だけでなく、スタブへの実リクエスト数（`searchCount`）も同時に検証する
 * （ヘッダの assert だけだと、キャッシュ読み出しが壊れて実際は毎回 GitHub API を叩いていても
 * ヘッダの文字列だけは辻褄が合ってしまう抜け道がある）。キーワードは他テスト・retry 試行との
 * 衝突を避けるため実行のたびに一意生成する（`uniqueKeyword`）。
 */
test('SP-5: /api/search が X-Cache-Status ヘッダで HIT/MISS を報告する', async ({ request }) => {
  const params = { q: uniqueKeyword('sp5-route-header-check'), page: '1' }

  await resetStubStats()

  const first = await request.get('/api/search', { params })
  expect(first.ok()).toBe(true)
  expect(first.headers()['x-cache-status']).toBe('MISS')
  expect((await readStubStats()).searchCount).toBe(1)

  const second = await request.get('/api/search', { params })
  expect(second.ok()).toBe(true)
  expect(second.headers()['x-cache-status']).toBe('HIT')
  expect((await readStubStats()).searchCount).toBe(1)
})
