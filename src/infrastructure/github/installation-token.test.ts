// @vitest-environment node
// jsdom の crypto/Uint8Array はグローバル環境（globalThis）と別レルムになり、
// jose の webapi 実装が payload の instanceof Uint8Array 判定で失敗する。
// このファイルは DOM に依存しないため node 環境で実行する。
import { decodeJwt, exportPKCS8, generateKeyPair } from 'jose'
import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ClockPort } from '../../domain/ports/clock-port'
import { makeInstallationTokenProvider, resetInstallationTokenCache } from './installation-token'

const FIXED_NOW = new Date('2026-08-19T00:00:00.000Z')
const TOKEN_EXPIRY_MARGIN_MS = 60_000
const ACCESS_TOKENS_URL = 'https://api.github.com/app/installations/installation-id/access_tokens'

function fixedClock(date: Date): ClockPort {
  return { now: () => date }
}

function stubCredentials(privateKeyPkcs8: string) {
  vi.stubEnv('GITHUB_APP_CLIENT_ID', 'client-id')
  vi.stubEnv('GITHUB_APP_INSTALLATION_ID', 'installation-id')
  vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', privateKeyPkcs8)
}

let privateKeyPkcs8: string
const server = setupServer()

beforeAll(async () => {
  const { privateKey } = await generateKeyPair('RS256', { extractable: true })
  privateKeyPkcs8 = await exportPKCS8(privateKey)
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  server.resetHandlers()
  resetInstallationTokenCache()
  vi.unstubAllEnvs()
})

afterAll(() => server.close())

describe('makeInstallationTokenProvider', () => {
  it('資格情報が揃っていなければ null を返す', async () => {
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')

    const provider = makeInstallationTokenProvider({ clock: fixedClock(FIXED_NOW) })

    await expect(provider()).resolves.toBeNull()
  })

  it('固定時刻から決定論的な iat / exp を持つ JWT で installation token を要求する', async () => {
    stubCredentials(privateKeyPkcs8)
    let capturedAuth: string | null = null
    server.use(
      http.post(ACCESS_TOKENS_URL, ({ request }) => {
        capturedAuth = request.headers.get('authorization')
        return HttpResponse.json({
          token: 'ghs_token',
          expires_at: new Date(FIXED_NOW.getTime() + 3_600_000).toISOString(),
        })
      }),
    )

    const provider = makeInstallationTokenProvider({ clock: fixedClock(FIXED_NOW) })
    const token = await provider()

    expect(token).toBe('ghs_token')
    expect(capturedAuth).not.toBeNull()

    const payload = decodeJwt(capturedAuth!.replace('Bearer ', ''))
    const fixedNowSeconds = Math.floor(FIXED_NOW.getTime() / 1000)
    expect(payload.iat).toBe(fixedNowSeconds - 60)
    expect(payload.exp).toBe(fixedNowSeconds + 540)
  })

  it('キャッシュ済みトークンが失効マージン（60秒）より手前なら再取得せずキャッシュを返す', async () => {
    stubCredentials(privateKeyPkcs8)
    let requestCount = 0
    server.use(
      http.post(ACCESS_TOKENS_URL, () => {
        requestCount += 1
        return HttpResponse.json({
          token: 'ghs_first',
          expires_at: new Date(FIXED_NOW.getTime() + 3_600_000).toISOString(),
        })
      }),
    )

    const first = await makeInstallationTokenProvider({ clock: fixedClock(FIXED_NOW) })()
    expect(first).toBe('ghs_first')
    expect(requestCount).toBe(1)

    // expiresAt - margin より 1 秒手前（まだ失効マージンに入っていない）
    const stillFresh = new Date(FIXED_NOW.getTime() + 3_600_000 - TOKEN_EXPIRY_MARGIN_MS - 1_000)
    const second = await makeInstallationTokenProvider({ clock: fixedClock(stillFresh) })()

    expect(second).toBe('ghs_first')
    expect(requestCount).toBe(1)
  })

  it('失効マージン境界を跨いだ時刻では再取得する', async () => {
    stubCredentials(privateKeyPkcs8)
    let requestCount = 0
    server.use(
      http.post(ACCESS_TOKENS_URL, () => {
        requestCount += 1
        return HttpResponse.json({
          token: requestCount === 1 ? 'ghs_first' : 'ghs_second',
          expires_at: new Date(FIXED_NOW.getTime() + 3_600_000).toISOString(),
        })
      }),
    )

    const first = await makeInstallationTokenProvider({ clock: fixedClock(FIXED_NOW) })()
    expect(first).toBe('ghs_first')
    expect(requestCount).toBe(1)

    // expiresAt - margin ちょうど（境界を跨いだ = マージン内）
    const atMargin = new Date(FIXED_NOW.getTime() + 3_600_000 - TOKEN_EXPIRY_MARGIN_MS)
    const second = await makeInstallationTokenProvider({ clock: fixedClock(atMargin) })()

    expect(second).toBe('ghs_second')
    expect(requestCount).toBe(2)
  })
})
