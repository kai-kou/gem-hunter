import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ErrorKind } from '@/src/domain/errors'
import { locale as toLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { toErrorPresentation } from './error-message'

const ja = getMessages('ja')
const en = getMessages('en')

/** 2026-08-20 18:30 JST（レート制限の復帰時刻として使う固定値）。 */
const RESET_AT = new Date('2026-08-20T09:30:00Z')

/**
 * 🔴 テストプロセスのタイムゾーンを UTC に固定する。
 *
 * 実装は `Asia/Tokyo` 固定で整形する（`datetime-rules.md` の JST 統一）。開発機・CI が JST だと
 * 実装から `timeZone` 指定が消えても同じ出力になり、退行を検知できない。本番の Workers は UTC で
 * 動くため、テストも UTC で回して「実装側の指定」だけが結果を決める状態にする。
 */
beforeAll(() => {
  vi.stubEnv('TZ', 'UTC')
})
afterAll(() => {
  vi.unstubAllEnvs()
})

describe('テスト環境の前提', () => {
  it('プロセスのタイムゾーンが UTC に固定されている（JST 表記は実装側の指定に由来する）', () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('UTC')
  })
})

describe.each([
  ['ja', ja],
  ['en', en],
] as const)('toErrorPresentation（%s）', (tag, messages) => {
  const locale = toLocale(tag)

  it('ネットワーク到達不可はカタログの文言をそのまま返し、ログイン導線は付けない（US-24）', () => {
    const result = toErrorPresentation('network', messages, { locale, isLoggedIn: false })

    expect(result.message).toBe(messages.common.errors.network)
    expect(result.loginHint).toBeUndefined()
  })

  it.each([
    ['auth', (m: typeof ja) => m.common.errors.auth],
    ['validation', (m: typeof ja) => m.common.errors.validation],
    ['notFound', (m: typeof ja) => m.common.errors.notFound],
    ['upstream', (m: typeof ja) => m.common.errors.upstream],
  ] as const)('%s はカタログの文言をそのまま返す（prd.md §7）', (kind, pick) => {
    const result = toErrorPresentation(kind as ErrorKind, messages, { locale, isLoggedIn: false })

    expect(result.message).toBe(pick(messages))
    expect(result.loginHint).toBeUndefined()
  })

  it('一次レート制限は復帰時刻を補間し、未ログインならログイン導線を添える（US-25 / AR-5）', () => {
    const result = toErrorPresentation('rateLimitPrimary', messages, {
      locale,
      retryAfter: RESET_AT,
      isLoggedIn: false,
    })

    expect(result.message).not.toContain('{resetAt}')
    expect(result.loginHint).toBe(messages.common.errors.rateLimitPrimaryLoginHint)
  })

  it('一次レート制限でもログイン済みならログイン導線を出さない（US-25）', () => {
    const result = toErrorPresentation('rateLimitPrimary', messages, {
      locale,
      retryAfter: RESET_AT,
      isLoggedIn: true,
    })

    expect(result.loginHint).toBeUndefined()
  })

  it('一次レート制限で復帰時刻が取れないときは UnknownReset 文言へフォールバックする', () => {
    const result = toErrorPresentation('rateLimitPrimary', messages, { locale, isLoggedIn: false })

    expect(result.message).toBe(messages.common.errors.rateLimitPrimaryUnknownReset)
    expect(result.loginHint).toBe(messages.common.errors.rateLimitPrimaryLoginHint)
  })

  it('二次レート制限は再試行までの秒数を補間する（prd.md §7）', () => {
    const result = toErrorPresentation('rateLimitSecondary', messages, {
      locale,
      retryAfterSeconds: 30,
      isLoggedIn: false,
    })

    expect(result.message).toContain('30')
    expect(result.message).not.toContain('{retryAfterSeconds}')
    expect(result.loginHint).toBeUndefined()
  })

  it('二次レート制限で秒数が取れないときは UnknownRetry 文言へフォールバックする', () => {
    const result = toErrorPresentation('rateLimitSecondary', messages, { locale, isLoggedIn: false })

    expect(result.message).toBe(messages.common.errors.rateLimitSecondaryUnknownRetry)
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
      const result = toErrorPresentation(kind, messages, {
        locale,
        retryAfter: RESET_AT,
        retryAfterSeconds: 30,
        isLoggedIn: false,
      })

      expect(result.message).not.toMatch(/\{\w+\}/)
    }
  })

  it('カタログの文言がロケールの言語で書かれている（ja / en の取り違え検知）', () => {
    const values = Object.values(messages.common.errors)
    const hasCjk = (text: string) => /[぀-ヿ一-鿿]/.test(text)

    expect(values.length).toBeGreaterThan(0)
    for (const value of values) {
      expect(hasCjk(value)).toBe(tag === 'ja')
    }
  })
})

describe('復帰時刻の表示（US-25 / datetime-rules.md）', () => {
  it('ja は基準タイムゾーンを明示する（JST 表記が無いと国外の利用者が自分の時刻と誤読する）', () => {
    const result = toErrorPresentation('rateLimitPrimary', ja, {
      locale: toLocale('ja'),
      retryAfter: RESET_AT,
      isLoggedIn: true,
    })

    expect(result.message).toContain('18:30')
    expect(result.message).toContain('JST')
  })

  it('en も基準タイムゾーンを明示する（12 時間表記 + オフセット）', () => {
    const result = toErrorPresentation('rateLimitPrimary', en, {
      locale: toLocale('en'),
      retryAfter: RESET_AT,
      isLoggedIn: true,
    })

    expect(result.message).toContain('06:30')
    expect(result.message).toMatch(/PM/)
    expect(result.message).toMatch(/GMT\+9/)
  })
})

describe('メッセージカタログの構造', () => {
  it('ja と en の errors キー構成が対称である', () => {
    expect(Object.keys(en.common.errors).sort()).toEqual(Object.keys(ja.common.errors).sort())
  })
})
