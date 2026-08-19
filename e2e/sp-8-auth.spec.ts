import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

/**
 * SP-8: GitHub OAuth ログインでレート枠が切り替わる（AR-5）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-8` の操作レビュー手順のうち
 * ログイン/ログアウト/レート枠切替を担当する（言語切替は `e2e/sp-8-locale.spec.ts`）。
 *
 * `src/ui/login-link.tsx` は `app/[locale]/layout.tsx` へまだ配線されていない（統合は別担当）
 * ため、ログイン/ログアウトは UI クリックではなく `/api/auth/{login,logout}` を直接叩く。
 * レート枠切替の観測は `/api/search`（`app/api/search/route.ts` がセッション Cookie を読む
 * 唯一の経路・SP-5 の X-Cache-Status 観測エンドポイントを流用）+ `/__stats` の
 * `userAuthSearchCount`（値が固定ユーザートークンと一致するリクエスト数）で行う
 * （未ログイン時も installation token の Authorization ヘッダが既に付いているため、
 * 「有無」ではなく「値」で判定する・whiteboard `sp8-auth-i18n-20260819` 争点 D round2 決定）。
 *
 * Step 0（T-1）は「`Secure` 属性 Cookie が `http://127.0.0.1` の E2E で実際に送受信されるか」
 * という未検証リスクの先行確認（round3 lead 裁定）。Chromium はループバックを
 * 「潜在的に信頼できるオリジン」として扱うため動作する想定だが、ここで実機確認する。
 * 🔴 本ファイルの E2E トポロジ（app・stub とも `127.0.0.1`）は same-site 判定になるため、
 * `SameSite=Lax` の cross-site 回帰検出はできない（`session-cookie.ts` 側のヘッダ文字列
 * assert が別途その役割を担う・login route.test.ts / callback route.test.ts）。
 */

const STUB_ORIGIN = `http://127.0.0.1:${process.env.E2E_STUB_PORT ?? '8788'}`
const SESSION_COOKIE_NAME = 'gem_hunter_session'

type StubStats = {
  searchCount: number
  detailCount: number
  userAuthSearchCount: number
  userAuthDetailCount: number
}

function uniqueKeyword(base: string): string {
  return `${base}-${randomBytes(4).toString('hex')}`
}

async function readStubStats(): Promise<StubStats> {
  const res = await fetch(`${STUB_ORIGIN}/__stats`)
  if (!res.ok) {
    throw new Error(`stub の /__stats が応答しない（status=${res.status}）`)
  }
  return (await res.json()) as StubStats
}

async function resetStubStats(): Promise<void> {
  const res = await fetch(`${STUB_ORIGIN}/__stats/reset`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`stub の /__stats/reset が応答しない（status=${res.status}）`)
  }
}

test('SP-8: 未ログインで全機能が使える／ログインでレート枠が切り替わる／ログアウトで元に戻る', async ({
  page,
  context,
}) => {
  await test.step('前提: スタブのリクエストカウントをリセットする', async () => {
    await resetStubStats()
  })

  await test.step('Step 0（T-1）: ダミー OAuth 経由でログインすると、実際にセッション Cookie が set される（Secure 属性の実機確認）', async () => {
    await page.goto('/api/auth/login')
    // authorize → stub の 302 → callback → セッション Cookie 発行 → '/' → '/ja' まで
    // ブラウザが自動でリダイレクトを辿る。
    await expect(page).toHaveURL(/\/ja(\?.*)?$/)

    const cookies = await context.cookies()
    const session = cookies.find((c) => c.name === SESSION_COOKIE_NAME)

    expect(session, 'セッション Cookie が set されていること').toBeTruthy()
    expect(session?.httpOnly).toBe(true)
    expect(session?.secure).toBe(true)
    expect(session?.sameSite).toBe('Lax')
    // oauth_state は使い捨てで即削除されているはず。
    expect(cookies.find((c) => c.name === 'oauth_state')).toBeUndefined()
  })

  await test.step('Step 2: ログイン中に検索すると、レート枠がユーザー自身のものに切り替わる（/__stats の userAuthSearchCount）', async () => {
    const keyword = uniqueKeyword('sp8-auth-check')

    const before = await readStubStats()
    // `page.request` の Cookie 送出が実機で不安定だったため、ブラウザの fetch
    // （同一オリジンで自動的に Cookie が付く・実ユーザーの挙動と同じ）で叩く。
    const status = await page.evaluate(
      async (q) => (await fetch(`/api/search?q=${encodeURIComponent(q)}`)).status,
      keyword,
    )
    expect(status).toBe(200)
    const after = await readStubStats()

    expect(after.userAuthSearchCount).toBe(before.userAuthSearchCount + 1)
  })

  await test.step('Step 3: ログアウトするとセッション Cookie が破棄され元に戻る', async () => {
    await page.goto('/api/auth/logout')
    await expect(page).toHaveURL(/\/ja(\?.*)?$/)

    const cookies = await context.cookies()
    expect(cookies.find((c) => c.name === SESSION_COOKIE_NAME)).toBeUndefined()
  })

  await test.step('Step 3 続き: ログアウト後は検索してもユーザー自身のレート枠は使われない', async () => {
    const keyword = uniqueKeyword('sp8-auth-loggedout-check')

    const before = await readStubStats()
    const status = await page.evaluate(
      async (q) => (await fetch(`/api/search?q=${encodeURIComponent(q)}`)).status,
      keyword,
    )
    expect(status).toBe(200)
    const after = await readStubStats()

    expect(after.userAuthSearchCount).toBe(before.userAuthSearchCount)
  })
})

test('SP-8 Step 1: 未ログインのまま検索から詳細ページまで全機能が使える（回帰）', async ({ page }) => {
  await test.step('検索する', async () => {
    await page.goto('/ja')
    await searchFor(page, 'react')
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
  })

  await test.step('詳細ページへ遷移できる', async () => {
    await page.getByRole('link', { name: 'octostub/octo-widgets' }).click()
    await expect(page.getByRole('heading', { name: 'octostub/octo-widgets' })).toBeVisible()
  })
})
