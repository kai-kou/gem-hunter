import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * SP-8: GitHub OAuth ログインでレート枠が切り替わる（AR-5）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-8` の操作レビュー手順のうち
 * ログイン/ログアウト/レート枠切替を担当する（言語切替は `e2e/sp-8-locale.spec.ts`）。
 *
 * `src/ui/login-link.tsx` は `app/[locale]/layout.tsx` に配線済み。ログインはダミー OAuth の
 * リダイレクト連鎖をそのまま辿るため `/api/auth/login` への直接ナビゲーションで行うが、
 * **ログアウトは UI のログアウトボタンをクリックする経路で行う**（`page.goto('/api/auth/logout')`
 * のような GET 直叩きにしない）。理由: `app/api/auth/logout/route.ts` は POST 限定であり、
 * GET は 405 を返すだけで副作用を持たない（旧実装は GET を受け付けており、`next/link` の
 * `<Link href="/api/auth/logout">` を画面に表示しただけで自動プリフェッチが
 * `GET /api/auth/logout` を実行し、セッション Cookie を黙って破棄するバグがあった。
 * Playwright トレースで `307 GET /api/auth/logout?_rsc=...` → `set-cookie` 空文字化を実測して
 * 特定した）。現在の `login-link.tsx` はログイン済み表示を `<form method="post"
 * action="/api/auth/logout"><button type="submit">` に変更しており、本ファイルの Step 3 は
 * この `<button role="button">` をクリックする形に追随している。
 * レート枠切替の観測は `/api/search`（`app/api/search/route.ts` がセッション Cookie を読む
 * 唯一の経路・SP-5 の X-Cache-Status 観測エンドポイントを流用）+ `/__stats` の
 * `userAuthSearchCount`（値が固定ユーザートークンと一致するリクエスト数）で行う
 * （未ログイン時も installation token の Authorization ヘッダが既に付いているため、
 * 「有無」ではなく「値」で判定する・whiteboard `sp8-auth-i18n-20260819` 争点 D round2 決定）。
 *
 * Step 0（T-1）は「`Secure` 属性 Cookie が `http://127.0.0.1` の E2E で実際に送受信されるか」
 * という未検証リスクの先行確認（round3 lead 裁定）として設けた。実機確認の結果、Chromium は
 * 非 TLS 接続でも Secure Cookie を一旦は受理するが、その後の永続化が不安定（直後の fetch()
 * で消えることがある）と判明したため、`secure` 属性は実際の接続プロトコルから動的に決める方式
 * （`src/composition/auth.ts` の `isSecureConnection`）に変更した。本 E2E は http 接続のため
 * `secure: false` を確認する（`true` になることは各 route の `*.test.ts` が検証する）。
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

  await test.step('Step 0（T-1）: ダミー OAuth 経由でログインすると、実際にセッション Cookie が set される', async () => {
    await page.goto('/api/auth/login')
    // authorize → stub の 302 → callback → セッション Cookie 発行 → '/' → '/ja' まで
    // ブラウザが自動でリダイレクトを辿る。
    // 🔴 `expect(page).toHaveURL()` ではなく `page.waitForURL()` を使う: 前者は
    // ナビゲーション完了（Set-Cookie の反映含む）を待たずに URL 一致を検出することがある。
    await page.waitForURL(/\/ja(\?.*)?$/)

    const cookies = await context.cookies()
    const session = cookies.find((c) => c.name === SESSION_COOKIE_NAME)

    expect(session, 'セッション Cookie が set されていること').toBeTruthy()
    expect(session?.httpOnly).toBe(true)
    // 🔴 T-1（`Secure` 属性 Cookie が `http://127.0.0.1` で実際に送受信されるか）の実機確認で、
    // Chromium は非 TLS 接続でも Secure Cookie を一旦は受理するが、その後の永続化が不安定
    // （直後の fetch() で消えていることがある）と判明した。本番は Cloudflare Workers 経由で
    // 常に HTTPS のため、`secure` 属性は実際の接続プロトコルから動的に決める方式に変更した
    // （`src/composition/auth.ts` の `isSecureConnection`）。この E2E は http 接続のため
    // `secure: false` になるのが正しい挙動（HTTPS 時に true になることは
    // `login/route.test.ts` / `callback/route.test.ts` がユニットテストで検証する）。
    expect(session?.secure).toBe(false)
    expect(session?.sameSite).toBe('Lax')
    // oauth_state は使い捨てで即削除されているはず。
    expect(cookies.find((c) => c.name === 'oauth_state')).toBeUndefined()
  })

  await test.step('Step 2: ログイン中に検索すると、レート枠がユーザー自身のものに切り替わる（/__stats の userAuthSearchCount）', async () => {
    const before = await readStubStats()

    const keyword = uniqueKeyword('sp8-auth-check')
    const response = await page.goto(`/api/search?q=${encodeURIComponent(keyword)}`)
    expect(response?.status()).toBe(200)

    const after = await readStubStats()
    expect(
      after.userAuthSearchCount,
      'ユーザー自身のアクセストークンで検索できていること',
    ).toBeGreaterThan(before.userAuthSearchCount)
  })

  await test.step('Step 3: ログアウトするとセッション Cookie が破棄され元に戻る', async () => {
    // Step 2 で `/api/search`（JSON 応答）へ遷移済みのため、ログアウトボタンがある
    // 画面へ一度戻る。
    await page.goto('/ja')
    await page.getByRole('button', { name: ja.common.auth.logout }).click()
    // Step 0 と同じ理由で waitForURL を使う（ナビゲーション完了を待ってから Cookie を確認する）。
    await page.waitForURL(/\/ja(\?.*)?$/)

    const cookies = await context.cookies()
    expect(cookies.find((c) => c.name === SESSION_COOKIE_NAME)).toBeUndefined()
  })

  await test.step('Step 3 続き: ログアウト後は検索してもユーザー自身のレート枠は使われない', async () => {
    const keyword = uniqueKeyword('sp8-auth-loggedout-check')

    const before = await readStubStats()
    const response = await page.goto(`/api/search?q=${encodeURIComponent(keyword)}`)
    expect(response?.status()).toBe(200)
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

test('SP-8 回帰: ログイン後にページ内リンクのプリフェッチが走ってもセッションは失われない', async ({
  page,
  context,
}) => {
  await test.step('ダミー OAuth でログインする', async () => {
    await page.goto('/api/auth/login')
    await page.waitForURL(/\/ja(\?.*)?$/)
  })

  await test.step('ページを表示したまま、ビューポート内リンクのプリフェッチが走る猶予を与える', async () => {
    // `next/link` の自動プリフェッチはリンクを画面に描画した後に走る。ログアウト導線が
    // GET ベースのリンクだった旧実装では、この待機の間に `GET /api/auth/logout` が
    // プリフェッチされセッション Cookie が黙って破棄されていた（ファイル冒頭コメント参照）。
    await page.waitForLoadState('networkidle')
  })

  await test.step('再読み込みしてもログアウトボタン（＝ログイン状態）が残っている', async () => {
    await page.reload()
    await expect(page.getByRole('button', { name: ja.common.auth.logout })).toBeVisible()

    const cookies = await context.cookies()
    expect(
      cookies.find((c) => c.name === SESSION_COOKIE_NAME),
      'ページ表示・再読み込みだけではセッション Cookie が破棄されないこと',
    ).toBeTruthy()
  })
})

test('SP-8 回帰: /api/auth/logout への GET は 405 を返し副作用を持たない', async ({
  page,
  context,
}) => {
  await test.step('ダミー OAuth でログインする', async () => {
    await page.goto('/api/auth/login')
    await page.waitForURL(/\/ja(\?.*)?$/)
  })

  await test.step('GET でログアウトエンドポイントを叩いても 405 が返り、セッションは残る', async () => {
    // `context.request`（`page.request` と同一）はブラウザの Cookie ジャーを共有するため、
    // ここでの GET にもセッション Cookie が付いて送られる。
    const response = await page.request.get('/api/auth/logout', { maxRedirects: 0 })
    expect(response.status()).toBe(405)

    const cookies = await context.cookies()
    expect(
      cookies.find((c) => c.name === SESSION_COOKIE_NAME),
      'GET リクエストではセッション Cookie が破棄されないこと',
    ).toBeTruthy()
  })
})
