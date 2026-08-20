import { describe, expect, it, vi } from 'vitest'

import { RATE_LIMIT_PERIOD_SECONDS, WorkersRateLimit } from './rate-limit'

describe('WorkersRateLimit', () => {
  it('binding が未提供の環境では常に許可する（フォールバック）', async () => {
    const limiter = new WorkersRateLimit(undefined)
    await expect(limiter.consume('any-key')).resolves.toEqual({ allowed: true })
  })

  it('binding が success: true を返せば許可する（retryAfterSeconds は付けない）', async () => {
    const binding = { limit: vi.fn().mockResolvedValue({ success: true }) }
    const limiter = new WorkersRateLimit(binding)
    await expect(limiter.consume('k')).resolves.toEqual({ allowed: true })
    expect(binding.limit).toHaveBeenCalledWith({ key: 'k' })
  })

  it('binding が success: false を返せば既定 period（RATE_LIMIT_PERIOD_SECONDS）を retryAfterSeconds として拒否する', async () => {
    const binding = { limit: vi.fn().mockResolvedValue({ success: false }) }
    const limiter = new WorkersRateLimit(binding)
    await expect(limiter.consume('k')).resolves.toEqual({
      allowed: false,
      retryAfterSeconds: RATE_LIMIT_PERIOD_SECONDS,
    })
  })

  it('periodSeconds を指定すればその値を retryAfterSeconds に使う', async () => {
    const binding = { limit: vi.fn().mockResolvedValue({ success: false }) }
    const limiter = new WorkersRateLimit(binding, { periodSeconds: 30 })
    await expect(limiter.consume('k')).resolves.toEqual({ allowed: false, retryAfterSeconds: 30 })
  })

  it('key をそのまま binding へ渡す（利用者の生 IP を上位層で扱わない）', async () => {
    const binding = { limit: vi.fn().mockResolvedValue({ success: true }) }
    const limiter = new WorkersRateLimit(binding)
    await limiter.consume('hmac-abc123')
    expect(binding.limit).toHaveBeenCalledWith({ key: 'hmac-abc123' })
  })
})
