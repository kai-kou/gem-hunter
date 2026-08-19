import { describe, expect, it } from 'vitest'
import { cacheStatusStore, getCacheStatus, recordCacheStatus } from './cache-status-context'

describe('cache-status-context', () => {
  it('store が確立されていれば recordCacheStatus で書き込んだ値を getCacheStatus で読める', async () => {
    await cacheStatusStore.run({ status: undefined }, async () => {
      expect(getCacheStatus()).toBeUndefined()
      recordCacheStatus('MISS')
      expect(getCacheStatus()).toBe('MISS')
      recordCacheStatus('HIT')
      expect(getCacheStatus()).toBe('HIT')
    })
  })

  it('store が確立されていない（run の外側）場合、getCacheStatus は undefined を返す', () => {
    expect(getCacheStatus()).toBeUndefined()
  })

  it('store が確立されていない場合、recordCacheStatus は例外を投げずに素通りする', () => {
    expect(() => recordCacheStatus('HIT')).not.toThrow()
  })

  it('await をまたぐ非同期処理でも同一 run 内であれば store が引き継がれる（AsyncLocalStorage の伝播確認）', async () => {
    await cacheStatusStore.run({ status: undefined }, async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
      recordCacheStatus('HIT')
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(getCacheStatus()).toBe('HIT')
    })
  })

  it('ネストした run は内側の store を独立して持つ（外側には影響しない）', async () => {
    await cacheStatusStore.run({ status: undefined }, async () => {
      recordCacheStatus('MISS')
      await cacheStatusStore.run({ status: undefined }, async () => {
        expect(getCacheStatus()).toBeUndefined()
        recordCacheStatus('HIT')
        expect(getCacheStatus()).toBe('HIT')
      })
      expect(getCacheStatus()).toBe('MISS')
    })
  })
})
