import { afterEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '../domain/errors'

const detailFetch = vi.fn()
const getRepositoryDetailUseCase = vi.fn(() => detailFetch)
const getRepositoryReadmeUseCase = vi.fn()
vi.mock('./container', () => ({
  getRepositoryDetailUseCase: (...args: unknown[]) => getRepositoryDetailUseCase(...(args as [])),
  getRepositoryReadmeUseCase: (...args: unknown[]) => getRepositoryReadmeUseCase(...args),
}))

const enforceDetailRateLimit = vi.fn()
vi.mock('./rate-limit', () => ({
  enforceDetailRateLimit: (...args: unknown[]) => enforceDetailRateLimit(...args),
}))

// `headers()` は Workers/Next のリクエストスコープでしか動かないため固定の `Headers` を返す
// （`app/[locale]/gems/page.test.tsx` と同じ流儀）。中身は `enforceDetailRateLimit` が
// 受け取るだけで判定には使われないが、同一インスタンスがそのまま渡っていることは検証する。
const FIXED_HEADERS = new Headers()
vi.mock('next/headers', () => ({
  headers: async () => FIXED_HEADERS,
}))

// mock 定義後に import する（rate-limit.test.ts / search-guard.test.ts と同じ流儀）。
const { fetchRepositoryDetail, getRepositoryReadmeUseCase: reExportedReadmeUseCase } =
  await import('./detail-guard')

const ACCESS_TOKEN = 'session-token'
const INPUT = { owner: 'facebook', repo: 'react' }

afterEach(() => {
  vi.clearAllMocks()
})

describe('fetchRepositoryDetail（Issue #190: page.tsx に書かれていた「間引き→取得」の集約）', () => {
  it('レート制限超過時は RateLimitExceededError がそのまま伝播し、取得は呼ばれない', async () => {
    const rateLimitError = new RateLimitExceededError('rateLimitSecondary', {
      retryAfterSeconds: 60,
    })
    enforceDetailRateLimit.mockRejectedValue(rateLimitError)

    await expect(fetchRepositoryDetail(ACCESS_TOKEN, INPUT)).rejects.toBe(rateLimitError)

    expect(getRepositoryDetailUseCase).not.toHaveBeenCalled()
    expect(detailFetch).not.toHaveBeenCalled()
  })

  it('正常時はアクセストークンで組み立てたユースケースへ input をそのまま渡し、結果を返す', async () => {
    enforceDetailRateLimit.mockResolvedValue(undefined)
    const repository = { fullName: 'facebook/react' }
    detailFetch.mockResolvedValue(repository)

    const result = await fetchRepositoryDetail(ACCESS_TOKEN, INPUT)

    expect(result).toBe(repository)
    expect(getRepositoryDetailUseCase).toHaveBeenCalledWith(ACCESS_TOKEN)
    expect(detailFetch).toHaveBeenCalledWith(INPUT)
  })

  it('見つからない場合は null をそのまま返す', async () => {
    enforceDetailRateLimit.mockResolvedValue(undefined)
    detailFetch.mockResolvedValue(null)

    const result = await fetchRepositoryDetail(ACCESS_TOKEN, INPUT)

    expect(result).toBeNull()
  })

  it('順序契約: レート制限の消費 → 取得（取得より先に間引く）', async () => {
    const callOrder: string[] = []
    enforceDetailRateLimit.mockImplementation(async () => {
      callOrder.push('enforceDetailRateLimit')
    })
    detailFetch.mockImplementation(async () => {
      callOrder.push('detailFetch')
      return null
    })

    await fetchRepositoryDetail(ACCESS_TOKEN, INPUT)

    expect(callOrder).toEqual(['enforceDetailRateLimit', 'detailFetch'])
  })

  it('レート制限の呼び出しに headers() が返す Headers をそのまま渡す', async () => {
    enforceDetailRateLimit.mockResolvedValue(undefined)
    detailFetch.mockResolvedValue(null)

    await fetchRepositoryDetail(ACCESS_TOKEN, INPUT)

    expect(enforceDetailRateLimit).toHaveBeenCalledWith(FIXED_HEADERS)
  })
})

describe('getRepositoryReadmeUseCase の re-export（Issue #190 セルフレビュー: page.tsx の import を1行に保つ）', () => {
  it('container.ts の実体をそのまま転送する（レート制限は挟まない）', () => {
    const readmeUseCase = vi.fn()
    getRepositoryReadmeUseCase.mockReturnValue(readmeUseCase)

    const result = reExportedReadmeUseCase(ACCESS_TOKEN)

    expect(getRepositoryReadmeUseCase).toHaveBeenCalledWith(ACCESS_TOKEN)
    expect(result).toBe(readmeUseCase)
    expect(enforceDetailRateLimit).not.toHaveBeenCalled()
  })
})
