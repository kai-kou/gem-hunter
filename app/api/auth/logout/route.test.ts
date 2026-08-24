import { NextRequest } from 'next/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/src/composition/auth', () => ({
  SESSION_COOKIE_NAME: 'gem_hunter_session',
  OAUTH_STATE_COOKIE_NAME: 'oauth_state',
  resolveLandingHost: (requestHost: string) => requestHost,
  // 実装（src/composition/auth.ts の landingUrl）と同じ理由（オープンリダイレクト対策）。
  // このユニットテストでは resolveLandingHost 同様に Host ヘッダをそのまま使う素朴な実装で十分
  // （統合的な検証は src/composition/auth.test.ts の landingUrl 自体のテストが担う）。
  landingUrl: (request: NextRequest) => {
    const requestHost = request.headers.get('host') ?? request.nextUrl.host
    return new URL('/', `${request.nextUrl.protocol}//${requestHost}`)
  },
}))

describe('POST /api/auth/logout', () => {
  it("セッション Cookie と oauth_state Cookie を破棄して '/' へ遷移する", async () => {
    const { POST } = await import('./route')

    const request = new NextRequest('http://127.0.0.1:3100/api/auth/logout', {
      method: 'POST',
      headers: { cookie: 'gem_hunter_session=encrypted-value; oauth_state=leftover-state' },
    })
    const res = await POST(request)

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get('location')!).pathname).toBe('/')
    expect(res.cookies.get('gem_hunter_session')?.value).toBe('')
    expect(res.cookies.get('oauth_state')?.value).toBe('')
  })

  it('Cookie が無い状態でも安全に動く（冪等）', async () => {
    const { POST } = await import('./route')

    const request = new NextRequest('http://127.0.0.1:3100/api/auth/logout', { method: 'POST' })
    const res = await POST(request)

    expect(res.status).toBe(307)
  })
})

describe('GET /api/auth/logout', () => {
  it('GET ハンドラは export されていない（プリフェッチで副作用が起きないことの保証）', async () => {
    // Next.js は route module（`route.ts`）の export 名で HTTP メソッドを解決するため、
    // `GET` キーの不在がそのまま「GET リクエストはフレームワークにハンドリングされず
    // 405 になる」＝プリフェッチ耐性を意味する（実リクエストでの 405 確認は
    // `e2e/sp-8-auth.spec.ts` の回帰テストが担う）。
    const route = await import('./route')

    expect((route as { GET?: unknown }).GET).toBeUndefined()
  })
})
