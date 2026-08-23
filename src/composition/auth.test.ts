import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildGithubAuthorizeUrl,
  isAuthConfigured,
  isSecureConnection,
  resolveLandingHost,
} from './auth'

/** 32 バイトの固定ダミー鍵（base64url）。テスト専用（session-cookie.test.ts と同じ値）。 */
const VALID_KEY = 'Z2VtLWh1bnRlci10ZXN0LXNlc3Npb24ta2V5LTMyYgA'

function stubAllFourVars() {
  vi.stubEnv('GITHUB_OAUTH_CLIENT_ID', 'client-id')
  vi.stubEnv('GITHUB_OAUTH_CLIENT_SECRET', 'client-secret')
  vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'http://127.0.0.1:3100/api/auth/callback')
  vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
}

afterEach(() => vi.unstubAllEnvs())

describe('isAuthConfigured', () => {
  it('4変数すべて未設定なら false', () => {
    expect(isAuthConfigured()).toBe(false)
  })

  it('OAuth 3変数のみ揃い SESSION_ENCRYPTION_KEY が欠けていれば false（静かに壊れるのを防ぐ）', () => {
    vi.stubEnv('GITHUB_OAUTH_CLIENT_ID', 'client-id')
    vi.stubEnv('GITHUB_OAUTH_CLIENT_SECRET', 'client-secret')
    vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'http://127.0.0.1:3100/api/auth/callback')

    expect(isAuthConfigured()).toBe(false)
  })

  it('4変数すべて揃えば true', () => {
    stubAllFourVars()
    expect(isAuthConfigured()).toBe(true)
  })
})

describe('buildGithubAuthorizeUrl', () => {
  it('src/infrastructure/github/oauth.ts の buildAuthorizeUrl を薄く委譲する', () => {
    stubAllFourVars()
    const url = new URL(buildGithubAuthorizeUrl('state-xyz'))

    expect(url.searchParams.get('state')).toBe('state-xyz')
    expect(url.searchParams.get('client_id')).toBe('client-id')
  })
})

describe('isSecureConnection（PR #141 レビュー指摘: Secure属性は接続プロトコル由来）', () => {
  it('https ならtrue', () => {
    expect(isSecureConnection('https:')).toBe(true)
  })

  it('http ならfalse（Chromium が非TLS接続のSecure Cookieを不安定にしか保持しない実機問題への対応）', () => {
    expect(isSecureConnection('http:')).toBe(false)
  })
})

describe('resolveLandingHost（PR #141 レビュー指摘: オープンリダイレクト対策）', () => {
  it('GITHUB_OAUTH_CALLBACK_URL 未設定なら受信した Host をそのまま使う（後方互換）', () => {
    expect(resolveLandingHost('127.0.0.1:3100')).toBe('127.0.0.1:3100')
  })

  it('受信した Host が許可ホストと一致すればそのまま使う', () => {
    vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'http://127.0.0.1:3100/api/auth/callback')
    expect(resolveLandingHost('127.0.0.1:3100')).toBe('127.0.0.1:3100')
  })

  it('受信した Host が許可ホストと食い違うと許可ホスト側にフォールバックする（Host ヘッダ偽装対策）', () => {
    vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'https://gem-hunter.example/api/auth/callback')
    expect(resolveLandingHost('evil.example')).toBe('gem-hunter.example')
  })
})
