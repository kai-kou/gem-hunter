import { describe, expect, it } from 'vitest'

import type { CacheKey } from '../../domain/ports/cache-port'
import {
  CACHE_KEY_ORIGIN,
  WorkersCache,
  cacheKeyToRequest,
  workersCacheStorage,
  type WorkersCacheStorage,
} from './workers-cache'

/**
 * `WorkersCache` はキーの意味論を持たない（生成関数は `cache-key.ts` の責務）ため、
 * `cache.test.ts` と同じくテスト内では直接キャストする（意図的な例外＝テストヘルパー）。
 */
function testKey(raw: string): CacheKey {
  return raw as CacheKey
}

type PutRecord = {
  readonly url: string
  readonly method: string
  readonly cacheControl: string | null
  readonly body: string
}

/**
 * `caches.default` の fake。
 *
 * 🔴 終了値を差し替えるだけの fake にしない（`sprint-development-rules.md` `SD-2` / #710）:
 * `put` / `match` / `delete` が **実際に受け取った `Request` の URL と `Cache-Control`** を
 * 記録し、テスト側で assert できるようにする。TTL は `Cache-Control: max-age` を fake が
 * 解釈して期限判定するので、実装が誤った max-age を書けばテストが落ちる。
 */
function fakeCacheStorage(initialMs = 0) {
  let now = initialMs
  const entries = new Map<string, { body: string; expiresAt: number }>()
  const puts: PutRecord[] = []
  const matches: string[] = []
  const deletes: string[] = []
  let throwOnMatch: Error | undefined
  let throwOnPut: Error | undefined
  let throwOnDelete: Error | undefined

  const storage: WorkersCacheStorage = {
    async put(request: Request, response: Response): Promise<void> {
      if (throwOnPut) throw throwOnPut
      const cacheControl = response.headers.get('Cache-Control')
      const body = await response.text()
      puts.push({ url: request.url, method: request.method, cacheControl, body })
      const maxAge = /max-age=(\d+)/.exec(cacheControl ?? '')
      if (!maxAge) {
        // max-age が無いレスポンスは保存しない（実装が TTL を書き忘れたら HIT しなくなる）
        return
      }
      entries.set(request.url, { body, expiresAt: now + Number(maxAge[1]) * 1000 })
    },
    async match(request: Request): Promise<Response | undefined> {
      if (throwOnMatch) throw throwOnMatch
      matches.push(request.url)
      const entry = entries.get(request.url)
      if (!entry) return undefined
      if (entry.expiresAt <= now) {
        entries.delete(request.url)
        return undefined
      }
      return new Response(entry.body)
    },
    async delete(request: Request): Promise<boolean> {
      if (throwOnDelete) throw throwOnDelete
      deletes.push(request.url)
      return entries.delete(request.url)
    },
  }

  return {
    storage,
    puts,
    matches,
    deletes,
    advance(ms: number) {
      now += ms
    },
    failMatchWith(error: Error) {
      throwOnMatch = error
    },
    failPutWith(error: Error) {
      throwOnPut = error
    },
    failDeleteWith(error: Error) {
      throwOnDelete = error
    },
    /** Cache API が壊れた JSON を返す状況（他者が書いた・スキーマが変わった等）を作る */
    seedRaw(url: string, body: string, ttlSeconds: number) {
      entries.set(url, { body, expiresAt: now + ttlSeconds * 1000 })
    },
  }
}

describe('cacheKeyToRequest', () => {
  it('CacheKey を固定オリジン配下の GET Request へ写す', () => {
    const request = cacheKeyToRequest(testKey('search:v2:next.js:page=1'))
    expect(request.method).toBe('GET')
    expect(request.url.startsWith(CACHE_KEY_ORIGIN)).toBe(true)
  })

  it('キーを percent-encode するため、区切り文字を含むキーでも不正な URL にならない', () => {
    const request = cacheKeyToRequest(testKey('repository:v2:owner/name?x=1#f'))
    expect(request.url).toBe(`${CACHE_KEY_ORIGIN}repository%3Av2%3Aowner%2Fname%3Fx%3D1%23f`)
    // エンコードせず素朴に連結すると `?` 以降がクエリ・`#` 以降がフラグメントになり
    // 別キーと同じ URL へ潰れる。パス以外の成分が生えていないことを確認する。
    const url = new URL(request.url)
    expect(url.search).toBe('')
    expect(url.hash).toBe('')
  })

  it('異なるキーは異なる URL になる（衝突しない）', () => {
    const a = cacheKeyToRequest(testKey('search:v2:a/b'))
    const b = cacheKeyToRequest(testKey('search:v2:a%2Fb'))
    expect(a.url).not.toBe(b.url)
  })

  it('日本語などの非 ASCII を含むキーでも Request を生成できる', () => {
    const request = cacheKeyToRequest(testKey('search:v2:検索語'))
    expect(request.url).toBe(`${CACHE_KEY_ORIGIN}${encodeURIComponent('search:v2:検索語')}`)
  })
})

describe('WorkersCache', () => {
  it('未設定のキーは null を返す（MISS）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await expect(cache.get(testKey('missing'))).resolves.toBeNull()
    expect(fake.matches).toEqual([cacheKeyToRequest(testKey('missing')).url])
  })

  it('set した値を get で取得できる（HIT）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('k'), { hello: 'world' }, 60)
    await expect(cache.get(testKey('k'))).resolves.toEqual({ hello: 'world' })
  })

  it('set は TTL を Cache-Control: max-age として書き、キーの URL へ put する', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('search:v2:x'), ['a'], 60)
    expect(fake.puts).toHaveLength(1)
    expect(fake.puts[0]!.url).toBe(cacheKeyToRequest(testKey('search:v2:x')).url)
    expect(fake.puts[0]!.method).toBe('GET')
    expect(fake.puts[0]!.cacheControl).toBe('max-age=60')
  })

  it('TTL 経過後は null を返す（Cache API 側の期限切れ）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('k'), 'v', 10)
    fake.advance(10_000)
    await expect(cache.get(testKey('k'))).resolves.toBeNull()
  })

  it('TTL 経過前は値を返す', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('k'), 'v', 10)
    fake.advance(9_999)
    await expect(cache.get(testKey('k'))).resolves.toBe('v')
  })

  it('undefined を保存しても往復できる（JSON 直列化で値が消えない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('u'), undefined, 60)
    // 「未登録（null）」ではなく「undefined を保存済み」として往復すること
    await expect(cache.get(testKey('u'))).resolves.toBeUndefined()
    expect(fake.matches).toContain(cacheKeyToRequest(testKey('u')).url)
  })

  it('null を保存しても往復できる', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('n'), null, 60)
    await expect(cache.get(testKey('n'))).resolves.toBeNull()
  })

  it('キーが異なる値は混ざらない', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('a'), 'A', 60)
    await cache.set(testKey('b'), 'B', 60)
    await expect(cache.get(testKey('a'))).resolves.toBe('A')
    await expect(cache.get(testKey('b'))).resolves.toBe('B')
  })

  it('invalidate で削除できる', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('k'), 'v', 60)
    await cache.invalidate(testKey('k'))
    expect(fake.deletes).toEqual([cacheKeyToRequest(testKey('k')).url])
    await expect(cache.get(testKey('k'))).resolves.toBeNull()
  })

  it('存在しないキーの invalidate はエラーにならない（冪等）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await expect(cache.invalidate(testKey('missing'))).resolves.toBeUndefined()
    await expect(cache.invalidate(testKey('missing'))).resolves.toBeUndefined()
  })

  describe('set の TTL 入力検証（fail-open を作らない）', () => {
    it('ttlSeconds が NaN のとき RangeError を throw し、put もしない', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      await expect(cache.set(testKey('k'), 'v', Number.NaN)).rejects.toThrow(RangeError)
      expect(fake.puts).toHaveLength(0)
    })

    it('ttlSeconds が Infinity のとき RangeError を throw する', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      await expect(cache.set(testKey('k'), 'v', Number.POSITIVE_INFINITY)).rejects.toThrow(
        RangeError,
      )
      expect(fake.puts).toHaveLength(0)
    })

    it('ttlSeconds が 0 のとき RangeError を throw する', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      await expect(cache.set(testKey('k'), 'v', 0)).rejects.toThrow(RangeError)
      expect(fake.puts).toHaveLength(0)
    })

    it('ttlSeconds が負値のとき RangeError を throw する', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      await expect(cache.set(testKey('k'), 'v', -1)).rejects.toThrow(RangeError)
      expect(fake.puts).toHaveLength(0)
    })

    it('1 秒未満の TTL でも max-age は 1 以上の整数になる（0 に潰さない）', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      await cache.set(testKey('k'), 'v', 0.5)
      expect(fake.puts[0]!.cacheControl).toBe('max-age=1')
    })
  })

  describe('Cache API が失敗したときの振る舞い（get は throw しない）', () => {
    it('match が throw したら null を返す', async () => {
      const fake = fakeCacheStorage()
      fake.failMatchWith(new Error('cache unavailable'))
      const cache = new WorkersCache(fake.storage)
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    it('保存されている本文が JSON として壊れていたら null を返す', async () => {
      const fake = fakeCacheStorage()
      fake.seedRaw(cacheKeyToRequest(testKey('k')).url, 'not json', 60)
      const cache = new WorkersCache(fake.storage)
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    it('保存されている本文が想定の封筒形でなければ null を返す（null 本文）', async () => {
      const fake = fakeCacheStorage()
      fake.seedRaw(cacheKeyToRequest(testKey('k')).url, 'null', 60)
      const cache = new WorkersCache(fake.storage)
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    // 🔴 封筒形の検査が無いと、文字列・数値の本文は `.value` が `undefined` になるだけで
    // 例外にならず、「MISS（null）」ではなく「undefined を保存済み」として返ってしまう。
    it.each([
      ['文字列本文', '"just a string"'],
      ['数値本文', '42'],
    ])('保存されている本文が想定の封筒形でなければ null を返す（%s）', async (_label, body) => {
      const fake = fakeCacheStorage()
      fake.seedRaw(cacheKeyToRequest(testKey('k')).url, body, 60)
      const cache = new WorkersCache(fake.storage)
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
    })

    it('put が throw してもリクエストを壊さない（set は解決する）', async () => {
      const fake = fakeCacheStorage()
      fake.failPutWith(new Error('cache put failed'))
      const cache = new WorkersCache(fake.storage)
      await expect(cache.set(testKey('k'), 'v', 60)).resolves.toBeUndefined()
    })

    it('循環参照など直列化できない値でも set は throw しない', async () => {
      const fake = fakeCacheStorage()
      const cache = new WorkersCache(fake.storage)
      const circular: { self?: unknown } = {}
      circular.self = circular
      await expect(cache.set(testKey('k'), circular, 60)).resolves.toBeUndefined()
      expect(fake.puts).toHaveLength(0)
    })

    it('delete が throw しても invalidate は throw しない（冪等の契約）', async () => {
      const fake = fakeCacheStorage()
      fake.failDeleteWith(new Error('cache delete failed'))
      const cache = new WorkersCache(fake.storage)
      await expect(cache.invalidate(testKey('k'))).resolves.toBeUndefined()
    })
  })
})

describe('workersCacheStorage', () => {
  const original = (globalThis as { caches?: unknown }).caches

  function setCaches(value: unknown) {
    if (value === undefined) {
      delete (globalThis as { caches?: unknown }).caches
      return
    }
    ;(globalThis as { caches?: unknown }).caches = value
  }

  function restore() {
    setCaches(original)
  }

  it('caches が無い環境（Node / jsdom）では undefined を返す', () => {
    setCaches(undefined)
    try {
      expect(workersCacheStorage()).toBeUndefined()
    } finally {
      restore()
    }
  })

  it('ブラウザ相当の CacheStorage（default を持たない）では undefined を返す', () => {
    setCaches({ open: () => {}, match: () => {} })
    try {
      expect(workersCacheStorage()).toBeUndefined()
    } finally {
      restore()
    }
  })

  it('default が put/match/delete を揃えていなければ undefined を返す', () => {
    setCaches({ default: { match: () => {} } })
    try {
      expect(workersCacheStorage()).toBeUndefined()
    } finally {
      restore()
    }
  })

  it('Workers 相当の caches.default があればそれを返す', () => {
    const def = { put: () => {}, match: () => {}, delete: () => {} }
    setCaches({ default: def })
    try {
      expect(workersCacheStorage()).toBe(def)
    } finally {
      restore()
    }
  })
})
