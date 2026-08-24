import { afterEach, describe, expect, it, vi } from 'vitest'

import { DomainValidationError, RateLimitExceededError } from '../domain/errors'

const searchKeyword = vi.fn()
vi.mock('../domain/model/search-keyword', () => ({
  searchKeyword: (...args: unknown[]) => searchKeyword(...args),
}))

const enforceSearchRateLimit = vi.fn()
vi.mock('./rate-limit', () => ({
  enforceSearchRateLimit: (...args: unknown[]) => enforceSearchRateLimit(...args),
}))

// mock 定義後に import する（rate-limit.test.ts と同じ流儀）。
const { prepareSearchKeyword } = await import('./search-guard')

const HEADERS = new Headers()

afterEach(() => {
  vi.clearAllMocks()
})

describe('prepareSearchKeyword（Issue #604: page.tsx / route.ts に重複する「変換→枠消費」の集約）', () => {
  it('不正なキーワードは DomainValidationError が伝播し、レート制限は呼ばれない', async () => {
    const validationError = new DomainValidationError(
      'SearchKeyword',
      'react is:private',
      '検索キーワードに修飾子（名前:値 の形式）は使用できません。キーワードだけを入力してください',
    )
    searchKeyword.mockImplementation(() => {
      throw validationError
    })

    await expect(prepareSearchKeyword('react is:private', HEADERS)).rejects.toBe(validationError)

    expect(enforceSearchRateLimit).not.toHaveBeenCalled()
  })

  it('正当なキーワードでは変換済みの値オブジェクトを返し、レート制限がちょうど1回呼ばれる', async () => {
    searchKeyword.mockReturnValue('react')
    enforceSearchRateLimit.mockResolvedValue(undefined)

    const result = await prepareSearchKeyword('react', HEADERS)

    expect(result).toBe('react')
    expect(searchKeyword).toHaveBeenCalledWith('react')
    expect(enforceSearchRateLimit).toHaveBeenCalledTimes(1)
    expect(enforceSearchRateLimit).toHaveBeenCalledWith(HEADERS)
  })

  it('レート制限超過時は RateLimitExceededError がそのまま伝播する', async () => {
    searchKeyword.mockReturnValue('react')
    const rateLimitError = new RateLimitExceededError('rateLimitSecondary', {
      retryAfterSeconds: 60,
    })
    enforceSearchRateLimit.mockRejectedValue(rateLimitError)

    await expect(prepareSearchKeyword('react', HEADERS)).rejects.toBe(rateLimitError)
  })

  it('順序契約: 値オブジェクト変換 → レート制限消費（変換前に枠を消費しない）', async () => {
    const callOrder: string[] = []
    searchKeyword.mockImplementation((raw: string) => {
      callOrder.push('searchKeyword')
      return raw
    })
    enforceSearchRateLimit.mockImplementation(async () => {
      callOrder.push('enforceSearchRateLimit')
    })

    await prepareSearchKeyword('react', HEADERS)

    expect(callOrder).toEqual(['searchKeyword', 'enforceSearchRateLimit'])
  })
})
