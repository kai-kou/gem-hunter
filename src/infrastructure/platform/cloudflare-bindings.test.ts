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
 * Issue #875 の実機欠陥修正: プレビュー実機で `cf-ray` ヘッダから抽出する旧実装が常に
 * `null` だったため、`getCloudflareContext().cf.colo` から取得する方式へ切り替えた。
 */
describe('cloudflareColo', () => {
  it('cf.colo があればそれを返す（取れるとき）', async () => {
    getCloudflareContext.mockResolvedValue({ env: {}, cf: { colo: 'SJC' } })

    const { cloudflareColo } = await import('./cloudflare-bindings')
    await expect(cloudflareColo()).resolves.toBe('SJC')
    expect(getCloudflareContext).toHaveBeenCalledWith({ async: true })
  })

  it('getCloudflareContext が例外を投げたら undefined を返す（Workers 実行環境の外・取れないとき）', async () => {
    getCloudflareContext.mockRejectedValue(new Error('not in a Workers runtime'))

    const { cloudflareColo } = await import('./cloudflare-bindings')
    await expect(cloudflareColo()).resolves.toBeUndefined()
  })

  it('cf 自体が undefined なら undefined を返す（プレビュー実機の残存パターン）', async () => {
    getCloudflareContext.mockResolvedValue({ env: {}, cf: undefined })

    const { cloudflareColo } = await import('./cloudflare-bindings')
    await expect(cloudflareColo()).resolves.toBeUndefined()
  })

  it('cf はあるが colo フィールドが無ければ undefined を返す', async () => {
    getCloudflareContext.mockResolvedValue({ env: {}, cf: {} })

    const { cloudflareColo } = await import('./cloudflare-bindings')
    await expect(cloudflareColo()).resolves.toBeUndefined()
  })
})
