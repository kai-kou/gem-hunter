import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const isAuthConfiguredMock = vi.fn()
const completeLoginUseCaseMock = vi.fn()
const encodeSessionCookieMock = vi.fn()

const OAUTH_STATE_COOKIE_NAME = 'oauth_state'

vi.mock('@/src/composition/auth', () => ({
  isAuthConfigured: (...args: unknown[]) => isAuthConfiguredMock(...args),
  completeLoginUseCase: (...args: unknown[]) => completeLoginUseCaseMock(...args),
  encodeSessionCookie: (...args: unknown[]) => encodeSessionCookieMock(...args),
  OAUTH_STATE_COOKIE_NAME,
  // PR #141 レビュー指摘後: 実装は許可ホストと食い違う場合にフォールバックするが、
  // このユニットテストでは Host ヘッダをそのまま使う素朴な実装で十分（統合的な検証は
  // src/composition/auth.test.ts の resolveLandingHost 自体のテストが担う）。
  resolveLandingHost: (requestHost: string) => requestHost,
  // 実装と同じ判定（PR #141 レビュー指摘: secure 属性は接続プロトコル由来）。
  isSecureConnection: (protocol: string) => protocol === 'https:',
  SESSION_COOKIE_NAME: 'gem_hunter_session',
  SESSION_COOKIE_TTL_SECONDS: 604800,
}))

function makeRequest(pathAndQuery: string, cookieHeader?: string, base = 'http://127.0.0.1:3100') {
  const headers = cookieHeader ? { cookie: cookieHeader } : undefined
  return new NextRequest(new URL(pathAndQuery, base), { headers })
}

beforeEach(() => {
  isAuthConfiguredMock.mockReset()
  completeLoginUseCaseMock.mockReset()
  encodeSessionCookieMock.mockReset()
})

describe('GET /api/auth/callback', () => {
  it('未設定なら state 検証もトークン交換もせず失敗として遷移する', async () => {
    isAuthConfiguredMock.mockReturnValue(false)
    const { GET } = await import('./route')

    const res = await GET(
      makeRequest('/api/auth/callback?code=c&state=s', `${OAUTH_STATE_COOKIE_NAME}=s`),
    )

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get('location')!).pathname).toBe('/')
    expect(completeLoginUseCaseMock).not.toHaveBeenCalled()
    expect(res.cookies.get(OAUTH_STATE_COOKIE_NAME)?.value).toBe('')
  })

  it('code / state のいずれかが欠けていれば失敗として遷移する', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const { GET } = await import('./route')

    const res = await GET(makeRequest('/api/auth/callback?state=s', `${OAUTH_STATE_COOKIE_NAME}=s`))

    expect(res.status).toBe(307)
    expect(completeLoginUseCaseMock).not.toHaveBeenCalled()
  })

  it('state Cookie が無ければ失敗として遷移する', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const { GET } = await import('./route')

    const res = await GET(makeRequest('/api/auth/callback?code=c&state=s'))

    expect(res.status).toBe(307)
    expect(completeLoginUseCaseMock).not.toHaveBeenCalled()
  })

  it('クエリの state と Cookie の state が不一致なら失敗として遷移し、トークン交換しない（CSRF 対策）', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const { GET } = await import('./route')

    const res = await GET(
      makeRequest(
        '/api/auth/callback?code=c&state=attacker-state',
        `${OAUTH_STATE_COOKIE_NAME}=legit-state`,
      ),
    )

    expect(res.status).toBe(307)
    expect(completeLoginUseCaseMock).not.toHaveBeenCalled()
    expect(res.cookies.get(OAUTH_STATE_COOKIE_NAME)?.value).toBe('')
  })

  it("state が一致すればトークン交換し、セッション Cookie を発行して '/' へ遷移する（HTTPS 接続なら Secure を付ける）", async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const completeLogin = vi.fn().mockResolvedValue({ accessToken: 'gho_from_callback' })
    completeLoginUseCaseMock.mockReturnValue(completeLogin)
    encodeSessionCookieMock.mockResolvedValue('encrypted-session-value')

    const { GET } = await import('./route')
    const res = await GET(
      makeRequest(
        '/api/auth/callback?code=auth-code&state=match',
        `${OAUTH_STATE_COOKIE_NAME}=match`,
        'https://gem-hunter.example',
      ),
    )

    expect(completeLogin).toHaveBeenCalledWith('auth-code')
    expect(encodeSessionCookieMock).toHaveBeenCalledWith({ accessToken: 'gho_from_callback' })

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get('location')!).pathname).toBe('/')
    expect(res.cookies.get('gem_hunter_session')?.value).toBe('encrypted-session-value')
    expect(res.cookies.get(OAUTH_STATE_COOKIE_NAME)?.value).toBe('')

    const setCookie = res.headers.get('set-cookie') ?? ''
    expect(setCookie).toContain('HttpOnly')
    expect(setCookie).toContain('Secure')
    expect(setCookie.toLowerCase()).toContain('samesite=lax')
  })

  it('HTTP 接続（ローカル E2E 等）では Secure を付けない（PR #141 レビュー指摘: Chromium が非TLS接続のSecure Cookieを不安定にしか保持しない実機問題への対応）', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const completeLogin = vi.fn().mockResolvedValue({ accessToken: 'gho_http' })
    completeLoginUseCaseMock.mockReturnValue(completeLogin)
    encodeSessionCookieMock.mockResolvedValue('encrypted-session-value')

    const { GET } = await import('./route')
    const res = await GET(
      makeRequest(
        '/api/auth/callback?code=auth-code&state=match',
        `${OAUTH_STATE_COOKIE_NAME}=match`,
      ),
    )

    const setCookie = res.headers.get('set-cookie') ?? ''
    expect(setCookie).not.toContain('Secure')
  })

  it('トークン交換が失敗したら例外を外へ漏らさず失敗として遷移する', async () => {
    isAuthConfiguredMock.mockReturnValue(true)
    const completeLogin = vi.fn().mockRejectedValue(new Error('upstream error'))
    completeLoginUseCaseMock.mockReturnValue(completeLogin)

    const { GET } = await import('./route')
    const res = await GET(
      makeRequest(
        '/api/auth/callback?code=auth-code&state=match',
        `${OAUTH_STATE_COOKIE_NAME}=match`,
      ),
    )

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get('location')!).pathname).toBe('/')
    expect(res.cookies.get('gem_hunter_session')).toBeUndefined()
  })
})
