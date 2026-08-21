import { afterEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '../domain/errors'

const clientIpOf = vi.fn()
const hashRateLimitKey = vi.fn()
vi.mock('../infrastructure/platform/rate-limit-key', () => ({
  clientIpOf: (...args: unknown[]) => clientIpOf(...args),
  hashRateLimitKey: (...args: unknown[]) => hashRateLimitKey(...args),
}))

const rateLimiterBinding = vi.fn()
vi.mock('../infrastructure/platform/cloudflare-bindings', () => ({
  rateLimiterBinding: (...args: unknown[]) => rateLimiterBinding(...args),
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

  /**
   * ②CRITICAL 修正（PR #293 セルフレビュー指摘）: `sort=gem-index` は 1 リクエストで
   * 最大 10 回の上流呼び出しに増幅するため、消費コストを呼び出し側から指定できるようにする。
   */
  describe('cost オプション（②CRITICAL・レート増幅対策）', () => {
    it('cost 省略時は既定 1 回だけ consume する（後方互換）', async () => {
      clientIpOf.mockReturnValue(IP)
      vi.stubEnv('RATE_LIMIT_SALT', SALT)
      rateLimiterBinding.mockResolvedValue(BINDING)
      hashRateLimitKey.mockResolvedValue('hashed-key')
      consume.mockResolvedValue({ allowed: true })

      await enforceSearchRateLimit(HEADERS)

      expect(consume).toHaveBeenCalledTimes(1)
    })

    it('cost=10 を指定すると 10 回 consume する（すべて許可）', async () => {
      clientIpOf.mockReturnValue(IP)
      vi.stubEnv('RATE_LIMIT_SALT', SALT)
      rateLimiterBinding.mockResolvedValue(BINDING)
      hashRateLimitKey.mockResolvedValue('hashed-key')
      consume.mockResolvedValue({ allowed: true })

      await expect(enforceSearchRateLimit(HEADERS, { cost: 10 })).resolves.toBeUndefined()

      expect(consume).toHaveBeenCalledTimes(10)
    })

    it('途中の消費で拒否されたら、それ以上 consume せず即座に例外を投げる', async () => {
      clientIpOf.mockReturnValue(IP)
      vi.stubEnv('RATE_LIMIT_SALT', SALT)
      rateLimiterBinding.mockResolvedValue(BINDING)
      hashRateLimitKey.mockResolvedValue('hashed-key')
      consume
        .mockResolvedValueOnce({ allowed: true })
        .mockResolvedValueOnce({ allowed: true })
        .mockResolvedValueOnce({ allowed: false, retryAfterSeconds: 42 })

      const error = await enforceSearchRateLimit(HEADERS, { cost: 10 }).catch((e) => e)

      expect(error).toBeInstanceOf(RateLimitExceededError)
      expect((error as RateLimitExceededError).kind).toBe('rateLimitSecondary')
      expect((error as RateLimitExceededError).retryAfterSeconds).toBe(42)
      // 3 回目で拒否されたら、4〜10 回目は呼ばない。
      expect(consume).toHaveBeenCalledTimes(3)
    })

    it('フェイルオープン経路（IP 不明）は cost によらず consume を呼ばない', async () => {
      clientIpOf.mockReturnValue(null)
      vi.stubEnv('RATE_LIMIT_SALT', SALT)

      await expect(enforceSearchRateLimit(HEADERS, { cost: 10 })).resolves.toBeUndefined()

      expect(consume).not.toHaveBeenCalled()
    })

    it('フェイルオープン経路（salt 未設定）は cost によらず consume を呼ばない', async () => {
      clientIpOf.mockReturnValue(IP)
      vi.stubEnv('RATE_LIMIT_SALT', '')

      await expect(enforceSearchRateLimit(HEADERS, { cost: 10 })).resolves.toBeUndefined()

      expect(consume).not.toHaveBeenCalled()
    })

    it('フェイルオープン経路（binding 未提供）は cost によらず consume を呼ばない', async () => {
      clientIpOf.mockReturnValue(IP)
      vi.stubEnv('RATE_LIMIT_SALT', SALT)
      rateLimiterBinding.mockResolvedValue(undefined)

      await expect(enforceSearchRateLimit(HEADERS, { cost: 10 })).resolves.toBeUndefined()

      expect(consume).not.toHaveBeenCalled()
    })
  })
})
