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
