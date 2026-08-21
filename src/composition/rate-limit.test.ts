import { afterEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '../domain/errors'

const clientIpOf = vi.fn()
const hashRateLimitKey = vi.fn()
vi.mock('../infrastructure/platform/rate-limit-key', () => ({
  clientIpOf: (...args: unknown[]) => clientIpOf(...args),
  hashRateLimitKey: (...args: unknown[]) => hashRateLimitKey(...args),
}))

const rateLimiterBinding = vi.fn()
const gemIndexRateLimiterBinding = vi.fn()
vi.mock('../infrastructure/platform/cloudflare-bindings', () => ({
  rateLimiterBinding: (...args: unknown[]) => rateLimiterBinding(...args),
  gemIndexRateLimiterBinding: (...args: unknown[]) => gemIndexRateLimiterBinding(...args),
}))

const consume = vi.fn()
const WorkersRateLimit = vi.fn().mockImplementation(function (this: { consume: typeof consume }) {
  this.consume = consume
})
vi.mock('../infrastructure/platform/rate-limit', () => ({
  RATE_LIMIT_PERIOD_SECONDS: 60,
  WorkersRateLimit,
}))

// mock 定義後に import する（vi.mock はホイストされるため import 順は問題ないが明示のため最後に置く）。
const { enforceSearchRateLimit } = await import('./rate-limit')

const HEADERS = new Headers()
const IP = '203.0.113.1'
const SALT = 'test-salt'
const BINDING = { limit: vi.fn() }

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllEnvs()
})

describe('enforceSearchRateLimit', () => {
  it('IP が取れないなら素通り（consume を呼ばない）', async () => {
    clientIpOf.mockReturnValue(null)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)

    await expect(enforceSearchRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
  })

  it('RATE_LIMIT_SALT 未設定なら素通り（binding も取りに行かない）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')

    await expect(enforceSearchRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
  })

  it('binding 未提供なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforceSearchRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
  })

  it('allowed: true なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await expect(enforceSearchRateLimit(HEADERS)).resolves.toBeUndefined()
  })

  it('allowed: false なら RateLimitExceededError(rateLimitSecondary) を投げる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: false, retryAfterSeconds: 60 })

    const error = await enforceSearchRateLimit(HEADERS).catch((e) => e)

    expect(error).toBeInstanceOf(RateLimitExceededError)
    expect((error as RateLimitExceededError).kind).toBe('rateLimitSecondary')
    expect((error as RateLimitExceededError).retryAfterSeconds).toBe(60)
  })

  it('キーは生 IP そのものではない（consume に渡す引数に IP 文字列を含めない）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(1)
    const [calledKey] = consume.mock.calls[0] as [string]
    expect(calledKey).not.toContain(IP)
    expect(calledKey).toBe('search:hashed-key')
    expect(hashRateLimitKey).toHaveBeenCalledWith(IP, SALT)
  })

  it('sort 省略時は従来どおり通常バインディング（rateLimiterBinding）だけを取りに行く', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS)

    expect(rateLimiterBinding).toHaveBeenCalledTimes(1)
    expect(gemIndexRateLimiterBinding).not.toHaveBeenCalled()
  })
})

/**
 * SP-16 争点6: `sort=gemIndex` は 1 検索が最大 10 回の upstream 呼び出しになる（全件取得）ため、
 * `enforceSearchRateLimit` が sort を見て別スロット（低い上限の gemIndexRateLimiterBinding）で
 * 消費することを検証する（whiteboard round3 lead 裁定）。
 */
describe('enforceSearchRateLimit — sort=gemIndex 専用スロット', () => {
  it('sort=gemIndex なら通常バインディングではなく gemIndexRateLimiterBinding を取りに行く', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    gemIndexRateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS, 'gemIndex')

    expect(gemIndexRateLimiterBinding).toHaveBeenCalledTimes(1)
    expect(rateLimiterBinding).not.toHaveBeenCalled()
  })

  it('sort=gemIndex は通常検索と別名前空間のキーで消費する（枠を共有しない）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    gemIndexRateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS, 'gemIndex')

    expect(consume).toHaveBeenCalledTimes(1)
    const [calledKey] = consume.mock.calls[0] as [string]
    expect(calledKey).not.toBe('search:hashed-key')
    expect(calledKey).toBe('search-gem-index:hashed-key')
  })

  it('gemIndexRateLimiterBinding が未提供（wrangler.jsonc 未反映のローカル実行等）なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    gemIndexRateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforceSearchRateLimit(HEADERS, 'gemIndex')).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
  })

  it('gemIndex スロットも allowed: false なら RateLimitExceededError(rateLimitSecondary) を投げる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    gemIndexRateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: false, retryAfterSeconds: 60 })

    const error = await enforceSearchRateLimit(HEADERS, 'gemIndex').catch((e) => e)

    expect(error).toBeInstanceOf(RateLimitExceededError)
    expect((error as RateLimitExceededError).kind).toBe('rateLimitSecondary')
  })

  it("sort が 'gemIndex' 以外（relevance/stars/updated/不正値）なら通常バインディングを使う", async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS, 'stars')

    expect(rateLimiterBinding).toHaveBeenCalledTimes(1)
    expect(gemIndexRateLimiterBinding).not.toHaveBeenCalled()
  })
})
