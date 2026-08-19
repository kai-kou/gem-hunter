import { beforeEach, describe, expect, it, vi } from 'vitest'

const isAuthConfiguredMock = vi.fn()
const buildGithubAuthorizeUrlMock = vi.fn()

vi.mock('@/src/composition/auth', () => ({
  isAuthConfigured: (...args: unknown[]) => isAuthConfiguredMock(...args),
  buildGithubAuthorizeUrl: (...args: unknown[]) => buildGithubAuthorizeUrlMock(...args),
}))

beforeEach(() => {
  isAuthConfiguredMock.mockReset()
  buildGithubAuthorizeUrlMock.mockReset()
})

describe('GET /api/auth/login', () => {
  it('未設定（4変数が揃っていない）なら 404', async () => {
    isAuthConfiguredMock.mockReturnValue(false)
    const { GET } = await import('./route')

    const res = await GET()

    expect(res.status).toBe(404)
    expect(buildGithubAuthorizeUrlMock).not.toHaveBeenCalled()
  })

  it('設定済みなら authorize URL へ 302 リダイレクトし oauth_state Cookie を発行する', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    buildGithubAuthorizeUrlMock.mockImplementation(
      (state: string) => `https://github.com/login/oauth/authorize?state=${state}`,
    )
    const { GET, OAUTH_STATE_COOKIE_NAME } = await import('./route')

    const res = await GET()

    expect(res.status).toBe(307)
    const location = res.headers.get('location')
    expect(location).toMatch(/^https:\/\/github\.com\/login\/oauth\/authorize\?state=/)

    const stateInUrl = new URL(location!).searchParams.get('state')
    expect(stateInUrl).toBeTruthy()
    expect(buildGithubAuthorizeUrlMock).toHaveBeenCalledWith(stateInUrl)

    const setCookie = res.headers.get('set-cookie') ?? ''
    expect(setCookie).toContain(`${OAUTH_STATE_COOKIE_NAME}=${stateInUrl}`)
    expect(setCookie).toContain('HttpOnly')
    expect(setCookie).toContain('Secure')
    expect(setCookie.toLowerCase()).toContain('samesite=lax')
    expect(setCookie).toContain('Max-Age=600')
  })

  it('毎回異なる state を発行する（固定値の再利用は CSRF 対策として不十分）', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    buildGithubAuthorizeUrlMock.mockImplementation((state: string) => `https://github.com/x?state=${state}`)
    const { GET } = await import('./route')

    const first = await GET()
    const second = await GET()

    const firstState = new URL(first.headers.get('location')!).searchParams.get('state')
    const secondState = new URL(second.headers.get('location')!).searchParams.get('state')
    expect(firstState).not.toBe(secondState)
  })
})
