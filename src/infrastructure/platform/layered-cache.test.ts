import { describe, expect, it } from 'vitest'

import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import { DEFAULT_REFILL_TTL_SECONDS, LayeredCache } from './layered-cache'

function testKey(raw: string): CacheKey {
  return raw as CacheKey
}

type SetCall = { key: string; value: unknown; ttlSeconds: number }

/**
 * `CachePort` の記録付き fake。
 *
 * 🔴 終了値の差し替えだけにしない（`SD-2` / #710）: `get` / `set` / `invalidate` の
 * **呼び出し順と引数** を記録し、「primary HIT のとき secondary を一度も呼ばない」
 * のような **呼ばれなかったこと** まで assert できるようにする。
 */
function fakeCache(name: string) {
  const store = new Map<string, unknown>()
  const gets: string[] = []
  const sets: SetCall[] = []
  const invalidates: string[] = []
  let throwOnGet: Error | undefined
  let throwOnSet: Error | undefined
  let throwOnInvalidate: Error | undefined
  /** 同期 throw（Promise の rejection ではなく呼び出し時点で投げる）を再現するか */
  let throwSynchronously = false

  const port: CachePort = {
    async get<T>(key: CacheKey): Promise<T | null> {
      gets.push(key)
      if (throwOnGet) throw throwOnGet
      if (!store.has(key)) return null
      return store.get(key) as T
    },
    async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
      sets.push({ key, value, ttlSeconds })
      if (!Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
        throw new RangeError(`${name}: ttlSeconds は正の有限数である必要があります`)
      }
      if (throwOnSet) throw throwOnSet
      store.set(key, value)
    },
    async invalidate(key: CacheKey): Promise<void> {
      invalidates.push(key)
      if (throwOnInvalidate) throw throwOnInvalidate
      store.delete(key)
    },
  }

  return {
    name,
    store,
    gets,
    sets,
    invalidates,
    /** 同期 throw を再現する薄いラッパー（`Promise.all` に配列で渡す実装だと 2 つ目が呼ばれない） */
    get port(): CachePort {
      if (!throwSynchronously) return port
      return {
        get: (key) => {
          gets.push(key)
          throw throwOnGet ?? new Error(`${name}: get failed`)
        },
        set: (key, value, ttlSeconds) => {
          sets.push({ key, value, ttlSeconds })
          throw throwOnSet ?? new Error(`${name}: set failed`)
        },
        invalidate: (key) => {
          invalidates.push(key)
          throw throwOnInvalidate ?? new Error(`${name}: invalidate failed`)
        },
      }
    },
    seed(key: string, value: unknown) {
      store.set(key, value)
    },
    failGetWith(error: Error) {
      throwOnGet = error
    },
    failSetWith(error: Error) {
      throwOnSet = error
    },
    failInvalidateWith(error: Error) {
      throwOnInvalidate = error
    },
    failSynchronously() {
      throwSynchronously = true
    },
  }
}

describe('LayeredCache', () => {
  describe('get', () => {
    it('primary が HIT したら secondary を一度も呼ばない', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      primary.seed('k', 'from-primary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('k'))).resolves.toBe('from-primary')
      expect(primary.gets).toEqual(['k'])
      expect(secondary.gets).toEqual([])
    })

    it('primary MISS + secondary HIT なら secondary の値を返し、primary へ充填する', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.seed('k', 'from-secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('k'))).resolves.toBe('from-secondary')
      expect(secondary.gets).toEqual(['k'])
      expect(primary.sets).toEqual([
        { key: 'k', value: 'from-secondary', ttlSeconds: DEFAULT_REFILL_TTL_SECONDS },
      ])
    })

    it('充填後は同じ isolate の次の get で secondary を引かない', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.seed('k', 'from-secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await cache.get(testKey('k'))
      await expect(cache.get(testKey('k'))).resolves.toBe('from-secondary')

      // secondary を引いたのは最初の 1 回だけ（充填が効いている）
      expect(secondary.gets).toEqual(['k'])
    })

    it('充填の TTL はコンストラクタ引数で上書きできる', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.seed('k', 'v')
      const cache = new LayeredCache(primary.port, secondary.port, { refillTtlSeconds: 5 })

      await cache.get(testKey('k'))

      expect(primary.sets[0]?.ttlSeconds).toBe(5)
    })

    it('両方 MISS なら null を返す', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('missing'))).resolves.toBeNull()
      expect(primary.gets).toEqual(['missing'])
      expect(secondary.gets).toEqual(['missing'])
      expect(primary.sets).toEqual([])
    })

    it('secondary が undefined を保持していても HIT として扱い、primary へ充填する', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.seed('u', undefined)
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('u'))).resolves.toBeUndefined()
      expect(primary.sets).toHaveLength(1)
    })

    it('secondary の get が throw しても null を返す（get は throw しない）', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.failGetWith(new Error('secondary down'))
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    it('primary の get が throw しても secondary へフォールバックする（get は throw しない）', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      primary.failGetWith(new Error('primary down'))
      secondary.seed('k', 'from-secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('k'))).resolves.toBe('from-secondary')
      expect(secondary.gets).toEqual(['k'])
    })

    it('充填（primary への set）が失敗しても secondary の値を返す', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      primary.failSetWith(new Error('primary set failed'))
      secondary.seed('k', 'from-secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.get(testKey('k'))).resolves.toBe('from-secondary')
    })
  })

  describe('set', () => {
    it('primary と secondary の両方へ同じ値・同じ TTL で書く', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await cache.set(testKey('k'), { a: 1 }, 60)

      expect(primary.sets).toEqual([{ key: 'k', value: { a: 1 }, ttlSeconds: 60 }])
      expect(secondary.sets).toEqual([{ key: 'k', value: { a: 1 }, ttlSeconds: 60 }])
    })

    it('secondary の set が throw しても set 全体は成功し、primary には書けている', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.failSetWith(new Error('secondary set failed'))
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.set(testKey('k'), 'v', 60)).resolves.toBeUndefined()
      expect(primary.store.get('k')).toBe('v')
    })

    it('secondary が同期 throw しても set 全体は成功する', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.failSynchronously()
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.set(testKey('k'), 'v', 60)).resolves.toBeUndefined()
    })

    describe('TTL 入力検証（fail-open を作らない）', () => {
      it.each([
        ['NaN', Number.NaN],
        ['Infinity', Number.POSITIVE_INFINITY],
        ['0', 0],
        ['負値', -1],
      ])(
        'ttlSeconds が %s のとき RangeError を伝播し、どちらの層にも書かれない',
        async (_label, ttl) => {
          const primary = fakeCache('primary')
          const secondary = fakeCache('secondary')
          const cache = new LayeredCache(primary.port, secondary.port)

          await expect(cache.set(testKey('k'), 'v', ttl)).rejects.toThrow(RangeError)
          expect(primary.store.has('k')).toBe(false)
          expect(secondary.sets).toEqual([])
        },
      )
    })
  })

  describe('invalidate', () => {
    it('両方の層に対して実行する', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await cache.invalidate(testKey('k'))

      expect(primary.invalidates).toEqual(['k'])
      expect(secondary.invalidates).toEqual(['k'])
    })

    it('primary が throw しても secondary の invalidate は飛ばさない', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      primary.failInvalidateWith(new Error('primary invalidate failed'))
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
      expect(secondary.invalidates).toEqual(['k'])
    })

    it('primary が同期 throw しても secondary の invalidate は呼ばれる', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      primary.failSynchronously()
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
      expect(secondary.invalidates).toEqual(['k'])
    })

    it('secondary が throw しても invalidate は throw しない（冪等の契約）', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      secondary.failInvalidateWith(new Error('secondary invalidate failed'))
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
      expect(primary.invalidates).toEqual(['k'])
    })

    it('未登録キーでも throw しない（冪等）', async () => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')
      const cache = new LayeredCache(primary.port, secondary.port)

      await expect(cache.invalidate(testKey('missing'))).resolves.toBeUndefined()
      await expect(cache.invalidate(testKey('missing'))).resolves.toBeUndefined()
    })
  })

  describe('コンストラクタの入力検証', () => {
    it.each([
      ['NaN', Number.NaN],
      ['0', 0],
      ['負値', -1],
      ['Infinity', Number.POSITIVE_INFINITY],
    ])('refillTtlSeconds が %s なら生成時に RangeError（充填が黙って壊れない）', (_label, ttl) => {
      const primary = fakeCache('primary')
      const secondary = fakeCache('secondary')

      expect(
        () => new LayeredCache(primary.port, secondary.port, { refillTtlSeconds: ttl }),
      ).toThrow(RangeError)
    })
  })
})
