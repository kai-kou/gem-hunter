import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { UpstreamError } from '../../domain/errors'
import { buildAuthorizeUrl, makeGithubOAuth, oauthCredentialsConfigured } from './oauth'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  vi.unstubAllEnvs()
})
afterAll(() => server.close())

function stubCredentials() {
  vi.stubEnv('GITHUB_OAUTH_CLIENT_ID', 'client-id')
  vi.stubEnv('GITHUB_OAUTH_CLIENT_SECRET', 'client-secret')
  vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'http://127.0.0.1:3100/api/auth/callback')
}

describe('oauthCredentialsConfigured', () => {
  it('3変数のいずれかが欠けていれば false', () => {
    vi.stubEnv('GITHUB_OAUTH_CLIENT_ID', '')
    vi.stubEnv('GITHUB_OAUTH_CLIENT_SECRET', '')
    vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', '')
    expect(oauthCredentialsConfigured()).toBe(false)
  })

  it('3変数が揃っていれば true', () => {
    stubCredentials()
    expect(oauthCredentialsConfigured()).toBe(true)
  })
})

describe('buildAuthorizeUrl', () => {
  it('資格情報が無ければ例外を投げる', () => {
    expect(() => buildAuthorizeUrl('state-1')).toThrow()
  })

  it('client_id / redirect_uri / state を含み scope を付けない（no-scope）', () => {
    stubCredentials()
    const url = new URL(buildAuthorizeUrl('state-1'))

    expect(url.origin + url.pathname).toBe('https://github.com/login/oauth/authorize')
    expect(url.searchParams.get('client_id')).toBe('client-id')
    expect(url.searchParams.get('redirect_uri')).toBe('http://127.0.0.1:3100/api/auth/callback')
    expect(url.searchParams.get('state')).toBe('state-1')
    expect(url.searchParams.has('scope')).toBe(false)
  })

  it('GITHUB_OAUTH_ORIGIN でループバックへ差し替えられる（E2E スタブ用）', () => {
    stubCredentials()
    vi.stubEnv('GITHUB_OAUTH_ORIGIN', 'http://127.0.0.1:8788')

    const url = new URL(buildAuthorizeUrl('state-1'))
    expect(url.origin).toBe('http://127.0.0.1:8788')
  })

  it('GITHUB_OAUTH_ORIGIN がループバック以外なら例外を投げる（トークン流出防止）', () => {
    stubCredentials()
    vi.stubEnv('GITHUB_OAUTH_ORIGIN', 'https://evil.example.com')

    expect(() => buildAuthorizeUrl('state-1')).toThrow(/ループバック/)
  })
})

describe('makeGithubOAuth().exchangeAuthorizationCode', () => {
  it('資格情報が無ければ UpstreamError を投げる', async () => {
    await expect(makeGithubOAuth().exchangeAuthorizationCode('code-1')).rejects.toThrow(
      UpstreamError,
    )
  })

  it('トークン交換に成功したら accessToken を返す', async () => {
    stubCredentials()
    const capturedBodies: URLSearchParams[] = []
    server.use(
      http.post('https://github.com/login/oauth/access_token', async ({ request }) => {
        capturedBodies.push(new URLSearchParams(await request.text()))
        return HttpResponse.json({ access_token: 'gho_token', token_type: 'bearer', scope: '' })
      }),
    )

    const result = await makeGithubOAuth().exchangeAuthorizationCode('code-1')

    expect(result).toEqual({ accessToken: 'gho_token' })
    const [capturedBody] = capturedBodies
    expect(capturedBody.get('code')).toBe('code-1')
    expect(capturedBody.get('client_id')).toBe('client-id')
    expect(capturedBody.get('client_secret')).toBe('client-secret')
    expect(capturedBody.get('redirect_uri')).toBe('http://127.0.0.1:3100/api/auth/callback')
  })

  it('GitHub がエラー応答（error フィールド）を返したら UpstreamError を投げる', async () => {
    stubCredentials()
    server.use(
      http.post('https://github.com/login/oauth/access_token', () =>
        HttpResponse.json({ error: 'bad_verification_code', error_description: 'invalid code' }),
      ),
    )

    await expect(makeGithubOAuth().exchangeAuthorizationCode('bad-code')).rejects.toThrow(
      UpstreamError,
    )
  })

  it('access_token が欠落した応答なら UpstreamError を投げる', async () => {
    stubCredentials()
    server.use(
      http.post('https://github.com/login/oauth/access_token', () => HttpResponse.json({})),
    )

    await expect(makeGithubOAuth().exchangeAuthorizationCode('code-1')).rejects.toThrow(
      UpstreamError,
    )
  })

  it('HTTP エラーステータスなら UpstreamError を投げる', async () => {
    stubCredentials()
    server.use(
      http.post('https://github.com/login/oauth/access_token', () =>
        HttpResponse.json({ message: 'server error' }, { status: 500 }),
      ),
    )

    await expect(makeGithubOAuth().exchangeAuthorizationCode('code-1')).rejects.toThrow(
      UpstreamError,
    )
  })
})
