import { describe, expect, it } from 'vitest'

import {
  AuthError,
  DomainError,
  DomainValidationError,
  NetworkError,
  NotFoundError,
  RateLimitExceededError,
  UpstreamError,
} from './errors'

/**
 * `ErrorKind` は「利用者へ何をどう伝えるか」を層をまたいで判別するための唯一のキー
 * （prd.md §7 / SP-9）。UI 文言は kind から i18n で引くため、ここでは message ではなく
 * kind と再試行情報の契約だけを検証する。
 */
describe('ErrorKind', () => {
  it('各ドメインエラーが prd.md §7 の種別を kind として持つ', () => {
    expect(new DomainValidationError('SearchKeyword', '').kind).toBe('validation')
    expect(new UpstreamError('boom').kind).toBe('upstream')
    expect(new NotFoundError('none').kind).toBe('notFound')
    expect(new NetworkError('unreachable').kind).toBe('network')
    expect(new AuthError('forbidden').kind).toBe('auth')
    expect(new RateLimitExceededError('rateLimitPrimary').kind).toBe('rateLimitPrimary')
    expect(new RateLimitExceededError('rateLimitSecondary').kind).toBe('rateLimitSecondary')
  })

  it('すべて DomainError の派生である（境界で instanceof DomainError の一括判定ができる）', () => {
    const errors = [
      new DomainValidationError('SearchKeyword', ''),
      new UpstreamError('boom'),
      new NotFoundError('none'),
      new NetworkError('unreachable'),
      new AuthError('forbidden'),
      new RateLimitExceededError('rateLimitPrimary'),
    ]

    for (const error of errors) {
      expect(error).toBeInstanceOf(DomainError)
      expect(error).toBeInstanceOf(Error)
      expect(error.name).toBe(error.constructor.name)
    }
  })
})

describe('NetworkError', () => {
  it('cause を保持する（ログで原因を追えるようにする）', () => {
    const cause = new TypeError('fetch failed')

    expect(new NetworkError('到達できません', { cause }).cause).toBe(cause)
  })
})

describe('RateLimitExceededError', () => {
  it('一次レート制限は復帰時刻（retryAfter）を保持する', () => {
    const retryAfter = new Date('2026-08-20T12:00:00.000Z')

    const error = new RateLimitExceededError('rateLimitPrimary', { retryAfter })

    expect(error.retryAfter).toBe(retryAfter)
    expect(error.retryAfterSeconds).toBeUndefined()
  })

  it('二次レート制限は再試行までの秒数（retryAfterSeconds）を保持する', () => {
    const error = new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 })

    expect(error.retryAfterSeconds).toBe(60)
    expect(error.retryAfter).toBeUndefined()
  })

  it('再試行情報が無くても生成できる（秒数不明の 429）', () => {
    const error = new RateLimitExceededError('rateLimitSecondary')

    expect(error.retryAfter).toBeUndefined()
    expect(error.retryAfterSeconds).toBeUndefined()
    expect(error.message).not.toBe('')
  })

  it('開発者向けの message は差し替えられる（UI 文言は kind から引くため任意）', () => {
    const error = new RateLimitExceededError('rateLimitPrimary', { message: '独自メッセージ' })

    expect(error.message).toBe('独自メッセージ')
  })
})
