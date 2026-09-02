import { describe, expect, it } from 'vitest'

import type { CacheKey } from '../../domain/ports/cache-port'
import type { ClockPort } from '../../domain/ports/clock-port'
import { InMemoryCache } from './cache'

/**
 * `InMemoryCache` はキーの意味論を持たないため、テストでは生成関数を経由せず
 * リテラルを `CacheKey` へキャストする（Issue #89: 生成関数を経ないキーはコンパイルエラーに
 * なるべきだが、`InMemoryCache` 自体のテストは実装詳細ではなく汎用ストアとしての振る舞いを
 * 検証したいため、ここでの直接キャストは意図的な例外＝テストヘルパー）。
 */
function testKey(raw: string): CacheKey {
  return raw as CacheKey
}

/** テスト用の `ClockPort` フェイク（可変時刻）。 */
function fakeClock(initialMs: number): ClockPort & { advance(ms: number): void } {
  let current = initialMs
  return {
    now: () => new Date(current),
    advance: (ms: number) => {
      current += ms
    },
  }
}

describe('InMemoryCache', () => {
  it('set した値を get で取得できる', async () => {
    const cache = new InMemoryCache()
    await cache.set(testKey('k'), { hello: 'world' }, 60)
    await expect(cache.get(testKey('k'))).resolves.toEqual({ hello: 'world' })
  })

  it('未設定のキーは null を返す', async () => {
    const cache = new InMemoryCache()
    await expect(cache.get(testKey('missing'))).resolves.toBeNull()
  })

  it('TTL 経過後は null を返す（期限切れエントリは破棄される）', async () => {
    const clock = fakeClock(0)
    const cache = new InMemoryCache(clock)
    await cache.set(testKey('k'), 'v', 10)
    clock.advance(10_000)
    await expect(cache.get(testKey('k'))).resolves.toBeNull()
  })

  it('TTL 経過前は値を返す', async () => {
    const clock = fakeClock(0)
    const cache = new InMemoryCache(clock)
    await cache.set(testKey('k'), 'v', 10)
    clock.advance(9_999)
    await expect(cache.get(testKey('k'))).resolves.toBe('v')
  })

  it('invalidate で明示的に削除できる', async () => {
    const cache = new InMemoryCache()
    await cache.set(testKey('k'), 'v', 60)
    await cache.invalidate(testKey('k'))
    await expect(cache.get(testKey('k'))).resolves.toBeNull()
  })

  it('存在しないキーの invalidate はエラーにならない', async () => {
    const cache = new InMemoryCache()
    await expect(cache.invalidate(testKey('missing'))).resolves.toBeUndefined()
  })

  describe('set の TTL 入力検証', () => {
    it('ttlSeconds が NaN のとき throw する（fail-open 防止）', async () => {
      const cache = new InMemoryCache()
      await expect(cache.set(testKey('k'), 'v', Number.NaN)).rejects.toThrow(RangeError)
    })

    it('ttlSeconds が 0 のとき throw する', async () => {
      const cache = new InMemoryCache()
      await expect(cache.set(testKey('k'), 'v', 0)).rejects.toThrow(RangeError)
    })

    it('ttlSeconds が負値のとき throw する', async () => {
      const cache = new InMemoryCache()
      await expect(cache.set(testKey('k'), 'v', -1)).rejects.toThrow(RangeError)
    })
  })
})
