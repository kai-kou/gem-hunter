import { NextRequest } from 'next/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/src/composition/auth', () => ({
  SESSION_COOKIE_NAME: 'gem_hunter_session',
  OAUTH_STATE_COOKIE_NAME: 'oauth_state',
  resolveLandingHost: (requestHost: string) => requestHost,
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
    const route = await import('./route')

    expect((route as { GET?: unknown }).GET).toBeUndefined()
  })
})
