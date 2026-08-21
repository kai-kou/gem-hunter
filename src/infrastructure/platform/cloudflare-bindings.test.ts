import { describe, expect, it, vi } from 'vitest'

const getCloudflareContext = vi.fn()

vi.mock('@opennextjs/cloudflare', () => ({
  getCloudflareContext: (...args: unknown[]) => getCloudflareContext(...args),
}))

describe('rateLimiterBinding', () => {
  it('env.RATE_LIMITER があればそれを返す', async () => {
    const binding = { limit: vi.fn() }
    getCloudflareContext.mockResolvedValue({ env: { RATE_LIMITER: binding } })

    const { rateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(rateLimiterBinding()).resolves.toBe(binding)
    expect(getCloudflareContext).toHaveBeenCalledWith({ async: true })
  })

  it('getCloudflareContext が例外を投げたら undefined を返す（Workers 実行環境の外）', async () => {
    getCloudflareContext.mockRejectedValue(new Error('not in a Workers runtime'))

    const { rateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(rateLimiterBinding()).resolves.toBeUndefined()
  })

  it('env に RATE_LIMITER が無ければ undefined を返す', async () => {
    getCloudflareContext.mockResolvedValue({ env: {} })

    const { rateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(rateLimiterBinding()).resolves.toBeUndefined()
  })
})

/**
 * SP-16 争点6: `sort=gemIndex` 専用の別スロット（`wrangler.jsonc` の
 * `RATE_LIMITER_GEM_INDEX`）。`rateLimiterBinding` と同じ「binding 未提供・例外時は
 * undefined へ倒す」フォールバック方針を共有する。
 */
describe('gemIndexRateLimiterBinding', () => {
  it('env.RATE_LIMITER_GEM_INDEX があればそれを返す', async () => {
    const binding = { limit: vi.fn() }
    getCloudflareContext.mockResolvedValue({ env: { RATE_LIMITER_GEM_INDEX: binding } })

    const { gemIndexRateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(gemIndexRateLimiterBinding()).resolves.toBe(binding)
  })

  it('env.RATE_LIMITER と env.RATE_LIMITER_GEM_INDEX を混同しない', async () => {
    const normalBinding = { limit: vi.fn() }
    const gemIndexBinding = { limit: vi.fn() }
    getCloudflareContext.mockResolvedValue({
      env: { RATE_LIMITER: normalBinding, RATE_LIMITER_GEM_INDEX: gemIndexBinding },
    })

    const { rateLimiterBinding, gemIndexRateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(rateLimiterBinding()).resolves.toBe(normalBinding)
    await expect(gemIndexRateLimiterBinding()).resolves.toBe(gemIndexBinding)
  })

  it('getCloudflareContext が例外を投げたら undefined を返す（Workers 実行環境の外）', async () => {
    getCloudflareContext.mockRejectedValue(new Error('not in a Workers runtime'))

    const { gemIndexRateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(gemIndexRateLimiterBinding()).resolves.toBeUndefined()
  })

  it('env に RATE_LIMITER_GEM_INDEX が無ければ undefined を返す', async () => {
    getCloudflareContext.mockResolvedValue({ env: {} })

    const { gemIndexRateLimiterBinding } = await import('./cloudflare-bindings')
    await expect(gemIndexRateLimiterBinding()).resolves.toBeUndefined()
  })
})
