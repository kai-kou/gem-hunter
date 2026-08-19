import { NextRequest } from 'next/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/src/composition/auth', () => ({
  SESSION_COOKIE_NAME: 'gem_hunter_session',
}))

describe('GET /api/auth/logout', () => {
  it("セッション Cookie と oauth_state Cookie を破棄して '/' へ遷移する", async () => {
    const { GET } = await import('./route')

    const request = new NextRequest('http://127.0.0.1:3100/api/auth/logout', {
      headers: { cookie: 'gem_hunter_session=encrypted-value; oauth_state=leftover-state' },
    })
    const res = await GET(request)

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get('location')!).pathname).toBe('/')
    expect(res.cookies.get('gem_hunter_session')?.value).toBe('')
    expect(res.cookies.get('oauth_state')?.value).toBe('')
  })

  it('Cookie が無い状態でも安全に動く（冪等）', async () => {
    const { GET } = await import('./route')

    const request = new NextRequest('http://127.0.0.1:3100/api/auth/logout')
    const res = await GET(request)

    expect(res.status).toBe(307)
  })
})
