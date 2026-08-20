import { describe, expect, it } from 'vitest'

import { getMessages } from '@/src/shared/i18n/messages'
import { type ErrorKind, toErrorPresentation } from './error-message'

const ja = getMessages('ja')
const en = getMessages('en')

/** 2026-08-20 18:30 JST（レート制限の復帰時刻として使う固定値）。 */
const RESET_AT = new Date('2026-08-20T09:30:00Z')

describe('toErrorPresentation', () => {
  it('ネットワーク到達不可はカタログの文言をそのまま返し、ログイン導線は付けない（US-24）', () => {
    const result = toErrorPresentation('network', ja, { locale: 'ja', isLoggedIn: false })

    expect(result.message).toBe(ja.common.errors.network)
    expect(result.loginHint).toBeUndefined()
  })

  it.each([
    ['auth', (m: typeof ja) => m.common.errors.auth],
    ['validation', (m: typeof ja) => m.common.errors.validation],
    ['notFound', (m: typeof ja) => m.common.errors.notFound],
    ['upstream', (m: typeof ja) => m.common.errors.upstream],
  ] as const)('%s はカタログの文言をそのまま返す（prd.md §7）', (kind, pick) => {
    const result = toErrorPresentation(kind as ErrorKind, ja, { locale: 'ja', isLoggedIn: false })

    expect(result.message).toBe(pick(ja))
    expect(result.loginHint).toBeUndefined()
  })

  it('一次レート制限は復帰時刻を補間し、未ログインならログイン導線を添える（US-25 / AR-5）', () => {
    const result = toErrorPresentation('rateLimitPrimary', ja, {
      locale: 'ja',
      retryAfter: RESET_AT,
      isLoggedIn: false,
    })

    expect(result.message).toContain('18:30')
    expect(result.message).not.toContain('{resetAt}')
    expect(result.loginHint).toBe(ja.common.errors.rateLimitPrimaryLoginHint)
  })

  it('一次レート制限でもログイン済みならログイン導線を出さない（US-25）', () => {
    const result = toErrorPresentation('rateLimitPrimary', ja, {
      locale: 'ja',
      retryAfter: RESET_AT,
      isLoggedIn: true,
    })

    expect(result.message).toContain('18:30')
    expect(result.loginHint).toBeUndefined()
  })

  it('一次レート制限で復帰時刻が取れないときは UnknownReset 文言へフォールバックする', () => {
    const result = toErrorPresentation('rateLimitPrimary', ja, { locale: 'ja', isLoggedIn: false })

    expect(result.message).toBe(ja.common.errors.rateLimitPrimaryUnknownReset)
    expect(result.loginHint).toBe(ja.common.errors.rateLimitPrimaryLoginHint)
  })

  it('復帰時刻の書式はロケールに追従する（en は 12 時間表記）', () => {
    const result = toErrorPresentation('rateLimitPrimary', en, {
      locale: 'en',
      retryAfter: RESET_AT,
      isLoggedIn: true,
    })

    expect(result.message).toContain('06:30')
    expect(result.message).toMatch(/PM/)
  })

  it('二次レート制限は再試行までの秒数を補間する（prd.md §7）', () => {
    const result = toErrorPresentation('rateLimitSecondary', ja, {
      locale: 'ja',
      retryAfterSeconds: 30,
      isLoggedIn: false,
    })

    expect(result.message).toContain('30')
    expect(result.message).not.toContain('{retryAfterSeconds}')
    expect(result.loginHint).toBeUndefined()
  })

  it('二次レート制限で秒数が取れないときは UnknownRetry 文言へフォールバックする', () => {
    const result = toErrorPresentation('rateLimitSecondary', ja, {
      locale: 'ja',
      isLoggedIn: false,
    })

    expect(result.message).toBe(ja.common.errors.rateLimitSecondaryUnknownRetry)
  })

  it('どの種別でも未置換のプレースホルダーを残さない（NFR-9: 内部表現を出さない）', () => {
    const kinds: ErrorKind[] = [
      'network',
      'rateLimitPrimary',
      'rateLimitSecondary',
      'auth',
      'validation',
      'notFound',
      'upstream',
    ]

    for (const kind of kinds) {
      const result = toErrorPresentation(kind, en, {
        locale: 'en',
        retryAfter: RESET_AT,
        retryAfterSeconds: 30,
        isLoggedIn: false,
      })

      expect(result.message).not.toMatch(/\{\w+\}/)
    }
  })
})
