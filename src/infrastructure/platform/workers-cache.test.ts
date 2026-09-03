import { afterEach, describe, expect, it } from 'vitest'

import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import type { ClockPort } from '../../domain/ports/clock-port'
import { CACHE_HOST, TieredCache, WorkersCache, createSharedCache } from './workers-cache'
import type { TtlAwareCache } from './workers-cache'

function testKey(raw: string): CacheKey {
  return raw as CacheKey
}

/** テスト用の `ClockPort` フェイク（可変時刻・`cache.test.ts` の書き方を踏襲）。 */
function fakeClock(initialMs: number): ClockPort & { advance(ms: number): void } {
  let current = initialMs
  return {
    now: () => new Date(current),
    advance: (ms: number) => {
      current += ms
    },
  }
}

type FakeCacheOverrides = {
  match?: (request: RequestInfo | URL) => Promise<Response | undefined>
  put?: (request: RequestInfo | URL, response: Response) => Promise<void>
  delete?: (request: RequestInfo | URL) => Promise<boolean>
}

/**
 * `Cache`（Cloudflare Cache API）のテスト用フェイク。
 * 呼び出し引数（Request/Response 実体）を記録し、引数そのものへの assert を可能にする
 * （戻り値だけを差し替えるフェイクは put への Request/Response の内容検証を潰す変異を見逃す）。
 */
function createFakeCache(overrides: FakeCacheOverrides = {}) {
  const store = new Map<string, Response>()
  const calls = {
    match: [] as Array<RequestInfo | URL>,
    put: [] as Array<[RequestInfo | URL, Response]>,
    delete: [] as Array<RequestInfo | URL>,
  }

  const urlOf = (request: RequestInfo | URL): string =>
    request instanceof Request ? request.url : String(request)

  const cache = {
    match: async (request: RequestInfo | URL): Promise<Response | undefined> => {
      calls.match.push(request)
      if (overrides.match) {
        return overrides.match(request)
      }
      const stored = store.get(urlOf(request))
      return stored ? stored.clone() : undefined
    },
    put: async (request: RequestInfo | URL, response: Response): Promise<void> => {
      calls.put.push([request, response])
      if (overrides.put) {
        await overrides.put(request, response)
        return
      }
      store.set(urlOf(request), response.clone())
    },
    delete: async (request: RequestInfo | URL): Promise<boolean> => {
      calls.delete.push(request)
      if (overrides.delete) {
        return overrides.delete(request)
      }
      return store.delete(urlOf(request))
    },
    add: async () => {},
    addAll: async () => {},
    keys: async () => [],
    matchAll: async () => [],
  } as unknown as Cache

  return { cache, calls, store }
}

// `caches` は lib.dom.d.ts でグローバル変数として宣言されており（必須プロパティ扱い）、
// `delete` 演算子の対象にできない。テストでの差し替え・後片付けのみ `Record<string, unknown>`
// 経由で行う（実装側 `workers-cache.ts` は `typeof caches === 'undefined'` を型そのままに使う）。
type MutableGlobal = Record<string, unknown>

/** `caches` グローバルをフェイクへ差し替え、後片付け関数を返す。 */
function installFakeCaches(cache: Cache): () => void {
  const target = globalThis as unknown as MutableGlobal
  const hadOwnProperty = Object.prototype.hasOwnProperty.call(target, 'caches')
  const original = target.caches
  target.caches = { default: cache }
  return () => {
    if (hadOwnProperty) {
      target.caches = original
    } else {
      delete target.caches
    }
  }
}

afterEach(() => {
  // 保険: 各 it 内で uninstall するが、途中で失敗した場合に他テストへ漏らさない。
  delete (globalThis as unknown as MutableGlobal).caches
})

describe('WorkersCache', () => {
  describe('caches グローバルが未定義のとき', () => {
    it('get は null を返す', async () => {
      const cache = new WorkersCache({ clock: fakeClock(0) })
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    it('set は no-op で解決する', async () => {
      const cache = new WorkersCache({ clock: fakeClock(0) })
      await expect(cache.set(testKey('k'), 'v', 60)).resolves.toBeUndefined()
    })

    it('set は ttlSeconds が値域外なら RangeError を throw する（caches 未定義でも検証は行う）', async () => {
      const cache = new WorkersCache({ clock: fakeClock(0) })
      await expect(cache.set(testKey('k'), 'v', 0)).rejects.toThrow(RangeError)
      await expect(cache.set(testKey('k'), 'v', Number.NaN)).rejects.toThrow(RangeError)
      await expect(cache.set(testKey('k'), 'v', -1)).rejects.toThrow(RangeError)
    })

    it('invalidate は no-op で解決する', async () => {
      const cache = new WorkersCache({ clock: fakeClock(0) })
      await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
    })

    it('getWithTtl は null を返す', async () => {
      const cache = new WorkersCache({ clock: fakeClock(0) })
      await expect(cache.getWithTtl(testKey('k'))).resolves.toBeNull()
    })
  })

  describe('caches をフェイクへ差し替えたとき', () => {
    it('set → get で同じ値が往復する', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const cache = new WorkersCache({ clock: fakeClock(0) })
        await cache.set(testKey('k'), { hello: 'world' }, 60)
        await expect(cache.get(testKey('k'))).resolves.toEqual({ hello: 'world' })
      } finally {
        uninstall()
      }
    })

    it('put に渡す Request は GET・Response ヘッダに Cache-Control: max-age=<ttl> が載る', async () => {
      const { cache: fake, calls } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const cache = new WorkersCache({ clock: fakeClock(0) })
        await cache.set(testKey('k'), 'v', 42)
        expect(calls.put).toHaveLength(1)
        const [request, response] = calls.put[0]!
        expect(request).toBeInstanceOf(Request)
        expect((request as Request).method).toBe('GET')
        expect((request as Request).url).toBe(`${CACHE_HOST}/${encodeURIComponent('k')}`)
        expect(response.headers.get('Cache-Control')).toBe('max-age=42')
        expect(response.headers.get('Content-Type')).toBe('application/json')
      } finally {
        uninstall()
      }
    })

    it('match / put / delete が例外を投げても throw せず null / no-op になる', async () => {
      const { cache: fake } = createFakeCache({
        match: async () => {
          throw new Error('boom')
        },
        put: async () => {
          throw new Error('boom')
        },
        delete: async () => {
          throw new Error('boom')
        },
      })
      const uninstall = installFakeCaches(fake)
      try {
        const cache = new WorkersCache({ clock: fakeClock(0) })
        await expect(cache.get(testKey('k'))).resolves.toBeNull()
        await expect(cache.set(testKey('k'), 'v', 60)).resolves.toBeUndefined()
        await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
      } finally {
        uninstall()
      }
    })

    it('本文の JSON パース失敗時は null を返す', async () => {
      const { cache: fake } = createFakeCache({
        match: async () => new Response('not-json{{{', { status: 200 }),
      })
      const uninstall = installFakeCaches(fake)
      try {
        const cache = new WorkersCache({ clock: fakeClock(0) })
        await expect(cache.get(testKey('k'))).resolves.toBeNull()
      } finally {
        uninstall()
      }
    })

    it('期限切れ（expiresAt 到来済み）のペイロードは null になる', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const clock = fakeClock(0)
        const cache = new WorkersCache({ clock })
        await cache.set(testKey('k'), 'v', 10)
        clock.advance(10_000)
        await expect(cache.get(testKey('k'))).resolves.toBeNull()
      } finally {
        uninstall()
      }
    })

    it('期限切れ前は値を返す', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const clock = fakeClock(0)
        const cache = new WorkersCache({ clock })
        await cache.set(testKey('k'), 'v', 10)
        clock.advance(9_999)
        await expect(cache.get(testKey('k'))).resolves.toBe('v')
      } finally {
        uninstall()
      }
    })

    it('getWithTtl は残 TTL を秒単位（切り上げ）で返す', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const clock = fakeClock(0)
        const cache = new WorkersCache({ clock })
        await cache.set(testKey('k'), 'v', 60)
        clock.advance(10_000)
        await expect(cache.getWithTtl(testKey('k'))).resolves.toEqual({
          value: 'v',
          remainingTtlSeconds: 50,
        })
      } finally {
        uninstall()
      }
    })

    it('getWithTtl は残 TTL が 1 未満（期限切れ含む）なら null を返す', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const clock = fakeClock(0)
        const cache = new WorkersCache({ clock })
        await cache.set(testKey('k'), 'v', 10)
        clock.advance(10_000)
        await expect(cache.getWithTtl(testKey('k'))).resolves.toBeNull()
      } finally {
        uninstall()
      }
    })

    it('invalidate 後は get が null を返す', async () => {
      const { cache: fake } = createFakeCache()
      const uninstall = installFakeCaches(fake)
      try {
        const cache = new WorkersCache({ clock: fakeClock(0) })
        await cache.set(testKey('k'), 'v', 60)
        await cache.invalidate(testKey('k'))
        await expect(cache.get(testKey('k'))).resolves.toBeNull()
      } finally {
        uninstall()
      }
    })
  })
})

/** `CachePort` のテスト用フェイク（呼び出し引数を記録する）。 */
function fakeCachePort(initial: ReadonlyArray<[CacheKey, unknown]> = []): CachePort & {
  readonly calls: {
    readonly get: CacheKey[]
    readonly set: Array<[CacheKey, unknown, number]>
    readonly invalidate: CacheKey[]
  }
  readonly store: Map<CacheKey, unknown>
} {
  const store = new Map<CacheKey, unknown>(initial)
  const calls = {
    get: [] as CacheKey[],
    set: [] as Array<[CacheKey, unknown, number]>,
    invalidate: [] as CacheKey[],
  }
  return {
    calls,
    store,
    async get<T>(key: CacheKey): Promise<T | null> {
      calls.get.push(key)
      return store.has(key) ? (store.get(key) as T) : null
    },
    async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
      calls.set.push([key, value, ttlSeconds])
      store.set(key, value)
    },
    async invalidate(key: CacheKey): Promise<void> {
      calls.invalidate.push(key)
      store.delete(key)
    },
  }
}

/** `TtlAwareCache` のテスト用フェイク（`getWithTtl` を持つ版）。 */
function fakeTtlAwareCachePort(
  initial: ReadonlyArray<[CacheKey, unknown]> = [],
  ttlByKey: ReadonlyMap<CacheKey, number> = new Map(),
): TtlAwareCache & ReturnType<typeof fakeCachePort> & { readonly ttlCalls: CacheKey[] } {
  const base = fakeCachePort(initial)
  // `get` と別に記録する（後段 HIT 時の読み取り往復が 1 回で済んでいるかを数えるため）。
  const ttlCalls: CacheKey[] = []
  return {
    ...base,
    ttlCalls,
    async getWithTtl<T>(key: CacheKey): Promise<{ value: T; remainingTtlSeconds: number } | null> {
      ttlCalls.push(key)
      if (!base.store.has(key)) {
        return null
      }
      return {
        value: base.store.get(key) as T,
        remainingTtlSeconds: ttlByKey.get(key) ?? 60,
      }
    },
  }
}

describe('TieredCache', () => {
  it('前段 HIT で後段を引かない', async () => {
    const front = fakeCachePort([[testKey('k'), 'front-value']])
    const back = fakeCachePort([[testKey('k'), 'back-value']])
    const tiered = new TieredCache([front, back])
    await expect(tiered.get(testKey('k'))).resolves.toBe('front-value')
    expect(back.calls.get).toHaveLength(0)
  })

  it('後段 HIT で前段へ write-back され、以後は前段だけで HIT する', async () => {
    const front = fakeTtlAwareCachePort([])
    const back = fakeTtlAwareCachePort(
      [[testKey('k'), 'back-value']],
      new Map([[testKey('k'), 42]]),
    )
    const tiered = new TieredCache([front, back])

    await expect(tiered.get(testKey('k'))).resolves.toBe('back-value')
    expect(front.calls.set).toEqual([[testKey('k'), 'back-value', 42]])

    back.calls.get.length = 0
    await expect(tiered.get(testKey('k'))).resolves.toBe('back-value')
    expect(back.calls.get).toHaveLength(0)
  })

  it('後段（TtlAware）HIT 時の読み取り往復は合計 1 回（get → getWithTtl の 2 度読みをしない）', async () => {
    const front = fakeTtlAwareCachePort([])
    const back = fakeTtlAwareCachePort(
      [[testKey('k'), 'back-value']],
      new Map([[testKey('k'), 42]]),
    )
    const tiered = new TieredCache([front, back])

    await expect(tiered.get(testKey('k'))).resolves.toBe('back-value')

    // 🔴 後段は Cache API 実装（`WorkersCache`）が入る位置なので、読み取り往復が 2 倍になると
    // 後段 HIT のたびに無駄な I/O が発生する。`getWithTtl` 1 回で値と残 TTL の両方を得る。
    expect(back.calls.get.length + back.ttlCalls.length).toBe(1)
    expect(back.ttlCalls).toEqual([testKey('k')])
    expect(back.calls.get).toHaveLength(0)
    // write-back そのものは従来どおり行われる（最適化で挙動の外形を変えていないこと）
    expect(front.calls.set).toEqual([[testKey('k'), 'back-value', 42]])
  })

  it('残 TTL を返せない層（getWithTtl 未実装）からの write-back は行われない', async () => {
    const front = fakeCachePort([])
    const back = fakeCachePort([[testKey('k'), 'back-value']])
    const tiered = new TieredCache([front, back])
    await expect(tiered.get(testKey('k'))).resolves.toBe('back-value')
    expect(front.calls.set).toHaveLength(0)
  })

  it('set は全層へ書く', async () => {
    const a = fakeCachePort()
    const b = fakeCachePort()
    const tiered = new TieredCache([a, b])
    await tiered.set(testKey('k'), 'v', 30)
    expect(a.calls.set).toEqual([[testKey('k'), 'v', 30]])
    expect(b.calls.set).toEqual([[testKey('k'), 'v', 30]])
  })

  it('invalidate は全層から消す', async () => {
    const a = fakeCachePort([[testKey('k'), 'v']])
    const b = fakeCachePort([[testKey('k'), 'v']])
    const tiered = new TieredCache([a, b])
    await tiered.invalidate(testKey('k'))
    expect(a.calls.invalidate).toEqual([testKey('k')])
    expect(b.calls.invalidate).toEqual([testKey('k')])
  })

  it('不正な ttlSeconds で RangeError を throw する（層へは書かない）', async () => {
    const a = fakeCachePort()
    const b = fakeCachePort()
    const tiered = new TieredCache([a, b])
    await expect(tiered.set(testKey('k'), 'v', 0)).rejects.toThrow(RangeError)
    expect(a.calls.set).toHaveLength(0)
    expect(b.calls.set).toHaveLength(0)
  })
})

describe('createSharedCache', () => {
  it('前段（InMemoryCache）→ 後段（WorkersCache）の TieredCache を返し、set → get が往復する', async () => {
    const cache = createSharedCache(fakeClock(0))
    await cache.set(testKey('k'), 'v', 60)
    await expect(cache.get(testKey('k'))).resolves.toBe('v')
  })
})

describe('干渉検証（#725）: WorkersCache 単体の RangeError 契約は TieredCache 経由でも消えない', () => {
  it('WorkersCache.set と TieredCache.set の両方で不正 TTL が RangeError になる', async () => {
    const workers = new WorkersCache({ clock: fakeClock(0) })
    await expect(workers.set(testKey('k'), 'v', -5)).rejects.toThrow(RangeError)

    const tiered = new TieredCache([workers])
    await expect(tiered.set(testKey('k'), 'v', -5)).rejects.toThrow(RangeError)
  })
})
