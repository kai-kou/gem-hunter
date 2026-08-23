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
const { enforceSearchRateLimit, enforceGemListRateLimit } = await import('./rate-limit')

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

  it('1 リクエストにつき consume は 1 回だけ呼ぶ', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(1)
  })
})

describe('enforceGemListRateLimit', () => {
  it('IP が取れないなら素通り（consume を呼ばない）', async () => {
    clientIpOf.mockReturnValue(null)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)

    await expect(enforceGemListRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
  })

  it('RATE_LIMIT_SALT 未設定なら素通り（binding も取りに行かない）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')

    await expect(enforceGemListRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
  })

  it('binding 未提供なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforceGemListRateLimit(HEADERS)).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
  })

  it('allowed: true なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await expect(enforceGemListRateLimit(HEADERS)).resolves.toBeUndefined()
  })

  it('allowed: false なら RateLimitExceededError(rateLimitSecondary) を投げる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: false, retryAfterSeconds: 60 })

    const error = await enforceGemListRateLimit(HEADERS).catch((e) => e)

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

    await enforceGemListRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(1)
    const [calledKey] = consume.mock.calls[0] as [string]
    expect(calledKey).not.toContain(IP)
    expect(calledKey).toBe('gems:hashed-key')
    expect(hashRateLimitKey).toHaveBeenCalledWith(IP, SALT)
  })

  it('1 リクエストにつき consume は 1 回だけ呼ぶ', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceGemListRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(1)
  })
})

describe('検索と Gem 一覧の枠は独立している（Issue #442 のユーザー裁定）', () => {
  it('同じ IP・同じ salt でも consume に渡るキーの接頭辞が異なる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS)
    await enforceGemListRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(2)
    const [searchKey] = consume.mock.calls[0] as [string]
    const [gemListKey] = consume.mock.calls[1] as [string]

    expect(searchKey).toBe('search:hashed-key')
    expect(gemListKey).toBe('gems:hashed-key')
    // 同一ハッシュでも接頭辞が違えば Cloudflare 側のカウンタは別枠になる。
    // ここが同じキーに退行すると「検索 → Gem 一覧」の導線で枠を食い合う。
    expect(searchKey).not.toBe(gemListKey)
  })
})
