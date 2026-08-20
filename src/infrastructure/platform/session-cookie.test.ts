// @vitest-environment node
// jsdom の crypto/Uint8Array はグローバル環境（globalThis）と別レルムになり、jose の
// webapi 実装が payload の instanceof Uint8Array 判定で失敗する（installation-token.test.ts と同じ理由）。
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  decodeSessionCookie,
  encodeSessionCookie,
  sessionEncryptionConfigured,
  SESSION_COOKIE_TTL_SECONDS,
} from './session-cookie'

/** 32 バイトの固定ダミー鍵（base64url）。テスト専用。 */
const VALID_KEY = 'Z2VtLWh1bnRlci10ZXN0LXNlc3Npb24ta2V5LTMyYgA'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

describe('sessionEncryptionConfigured', () => {
  it('鍵未設定なら false', () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', '')
    expect(sessionEncryptionConfigured()).toBe(false)
  })

  it('32バイトの base64url 鍵が設定されていれば true', () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    expect(sessionEncryptionConfigured()).toBe(true)
  })

  it('長さが32バイトでない鍵は false 扱い', () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', 'dG9vLXNob3J0') // "too-short"
    expect(sessionEncryptionConfigured()).toBe(false)
  })
})

describe('encodeSessionCookie / decodeSessionCookie', () => {
  it('鍵未設定で encode すると例外を投げる', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', '')
    await expect(encodeSessionCookie({ accessToken: 'gho_token' })).rejects.toThrow()
  })

  it('往復（encode → decode）で同じ accessToken が復元される', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)

    const raw = await encodeSessionCookie({ accessToken: 'gho_roundtrip' })
    const decoded = await decodeSessionCookie(raw)

    expect(decoded).toEqual({ accessToken: 'gho_roundtrip' })
  })

  it('ペイロード（accessToken）は base64url でそのまま読めない（暗号化されている・NFR-9）', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)

    const raw = await encodeSessionCookie({ accessToken: 'gho_secret_value' })

    expect(raw).not.toContain('gho_secret_value')
    // JWE は 5 パート（header.encryptedKey.iv.ciphertext.tag）の compact serialization
    expect(raw.split('.')).toHaveLength(5)
  })

  it('鍵未設定で decode すると null', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    const raw = await encodeSessionCookie({ accessToken: 'gho_token' })

    vi.stubEnv('SESSION_ENCRYPTION_KEY', '')
    await expect(decodeSessionCookie(raw)).resolves.toBeNull()
  })

  it('改ざんされた値は null（例外を外へ漏らさない）', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    const raw = await encodeSessionCookie({ accessToken: 'gho_token' })
    const tampered = `${raw.slice(0, -4)}abcd`

    await expect(decodeSessionCookie(tampered)).resolves.toBeNull()
  })

  it('不正な文字列（そもそも JWE でない）は null', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    await expect(decodeSessionCookie('not-a-jwe')).resolves.toBeNull()
  })

  it('異なる鍵で暗号化された値は復号できず null', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    const raw = await encodeSessionCookie({ accessToken: 'gho_token' })

    vi.stubEnv('SESSION_ENCRYPTION_KEY', 'ZGlmZmVyZW50LWtleS1mb3ItdGVzdC0zMmIAAAAAAAA')
    await expect(decodeSessionCookie(raw)).resolves.toBeNull()
  })

  it('accessToken が空文字のペイロードを復号すると null（PR #141 レビュー指摘）', async () => {
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)
    const raw = await encodeSessionCookie({ accessToken: '' })

    await expect(decodeSessionCookie(raw)).resolves.toBeNull()
  })

  it('TTL（`exp`）を過ぎると null（期限切れは再ログインを要求する）', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-19T00:00:00.000Z'))
    vi.stubEnv('SESSION_ENCRYPTION_KEY', VALID_KEY)

    const raw = await encodeSessionCookie({ accessToken: 'gho_token' })

    vi.setSystemTime(new Date(Date.now() + (SESSION_COOKIE_TTL_SECONDS + 60) * 1000))
    await expect(decodeSessionCookie(raw)).resolves.toBeNull()
  })
})
