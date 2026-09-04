import { describe, expect, it, vi } from 'vitest'

import type { CacheKey } from '../../domain/ports/cache-port'
import {
  CACHE_KEY_ORIGIN,
  WorkersCache,
  cacheKeyToRequest,
  workersCacheStorage,
} from './workers-cache'
import { fakeCacheStorage } from './workers-cache.test-fake'

/**
 * `WorkersCache` はキーの意味論を持たない（生成関数は `cache-key.ts` の責務）ため、
 * `cache.test.ts` と同じくテスト内では直接キャストする（意図的な例外＝テストヘルパー）。
 */
function testKey(raw: string): CacheKey {
  return raw as CacheKey
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
      // 🔴 `ok` マーカーが無いと、`typeof === 'object'` を通過して `.value === undefined` になり
      //    「MISS」ではなく「undefined を保存済み」として HIT 扱いされる（PR #874 レビュー F2）。
      ['value を持たないオブジェクト本文', '{"foo":1}'],
      ['配列本文', '[]'],
      ['ok が false の本文', '{"ok":false,"value":1}'],
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

describe('WorkersCache — Date の往復（JSON では復元されない・PR #874 F1）', () => {
  it('Date を含む値を往復させても Date のまま返る（ISO 文字列に化けない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    const lastPushedAt = new Date('2026-08-15T03:00:00.000Z')

    await cache.set(testKey('d'), { items: [{ fullName: 'a/b', lastPushedAt }] }, 60)
    const got = await cache.get<{ items: { fullName: string; lastPushedAt: Date }[] }>(testKey('d'))

    // 🔴 `toEqual` だけでは ISO 文字列と Date を区別できない場合があるため、型と値を個別に見る。
    expect(got?.items[0]?.lastPushedAt).toBeInstanceOf(Date)
    expect(got?.items[0]?.lastPushedAt.getTime()).toBe(lastPushedAt.getTime())
    expect(got?.items[0]?.fullName).toBe('a/b')
  })

  it('トップレベルが Date でも往復する', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    const date = new Date('2026-01-02T03:04:05.000Z')

    await cache.set(testKey('top'), date, 60)
    const got = await cache.get<Date>(testKey('top'))

    expect(got).toBeInstanceOf(Date)
    expect(got?.getTime()).toBe(date.getTime())
  })

  it('Invalid Date は null になり、同じ値の他のフィールドは失われない（set 全体を壊さない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)

    await expect(
      cache.set(testKey('bad'), { name: 'x', at: new Date('not a date') }, 60),
    ).resolves.toBeUndefined()
    // 直列化が失敗して put ごと落ちていないこと（＝エントリが書かれている）
    expect(fake.puts).toHaveLength(1)
    await expect(cache.get(testKey('bad'))).resolves.toEqual({ name: 'x', at: null })
  })

  it('Date を含まない値の往復は素の JSON と同じ（余計なタグを混ぜない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)

    await cache.set(testKey('plain'), { a: 1, b: [true, 'x', null] }, 60)

    expect(fake.puts[0]!.body).toBe('{"ok":true,"value":{"a":1,"b":[true,"x",null]}}')
    await expect(cache.get(testKey('plain'))).resolves.toEqual({ a: 1, b: [true, 'x', null] })
  })
})

describe('WorkersCache — max-age の値域（不正な delta-seconds を書かない・PR #874 F3）', () => {
  it.each([
    ['1e21（指数表記に化ける値）', 1e21],
    ['2 ** 31（32bit 境界）', 2 ** 31],
    ['Number.MAX_SAFE_INTEGER', Number.MAX_SAFE_INTEGER],
  ])('%s でも Cache-Control は max-age=<整数> になる', async (_label, ttl) => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)

    await cache.set(testKey('k'), 'v', ttl)

    // 🔴 `max-age=1e+21` は RFC 9111 の delta-seconds として不正（受け側の解釈が実装依存になる）。
    expect(fake.puts[0]!.cacheControl).toMatch(/^max-age=\d+$/)
    // 上限（1 年）でクランプされていること
    expect(Number(/^max-age=(\d+)$/.exec(fake.puts[0]!.cacheControl ?? '')?.[1])).toBe(31_536_000)
    // 実際に保存され、HIT すること（fake は不正な max-age を保存しない）
    await expect(cache.get(testKey('k'))).resolves.toBe('v')
  })

  it('上限以下の TTL はそのまま書く（一律クランプではない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    await cache.set(testKey('k'), 'v', 3600)
    expect(fake.puts[0]!.cacheControl).toBe('max-age=3600')
  })
})

describe('WorkersCache — Cache API の失敗を無音にしない（PR #874 F4）', () => {
  it('put が失敗したら警告する。2 回失敗しても警告は 1 回だけ（isolate ごとに抑制）', async () => {
    const fake = fakeCacheStorage()
    fake.failPutWith(new Error('cache put failed'))
    const cache = new WorkersCache(fake.storage)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      await cache.set(testKey('search:v2:secret-keyword'), 'secret-value', 60)
      await cache.set(testKey('search:v2:another-keyword'), 'secret-value', 60)

      expect(warn).toHaveBeenCalledTimes(1)
      const [message, error] = warn.mock.calls[0]!
      expect(String(message)).toContain('[cache]')
      expect(String(message)).toContain('put')
      // 🔴 キー・値はログに出さない（キーは検索語を含み、値は API レスポンス本体）。
      expect(String(message)).not.toContain('secret-keyword')
      expect(String(message)).not.toContain('secret-value')
      expect(error).toBeInstanceOf(Error)
    } finally {
      warn.mockRestore()
    }
  })

  it('match が失敗したら警告する。2 回失敗しても警告は 1 回だけ', async () => {
    const fake = fakeCacheStorage()
    fake.failMatchWith(new Error('cache unavailable'))
    const cache = new WorkersCache(fake.storage)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      await expect(cache.get(testKey('a'))).resolves.toBeNull()
      await expect(cache.get(testKey('b'))).resolves.toBeNull()

      expect(warn).toHaveBeenCalledTimes(1)
      expect(String(warn.mock.calls[0]?.[0])).toContain('match')
    } finally {
      warn.mockRestore()
    }
  })

  it('put と match は別々に 1 回ずつ警告する（片方の抑制が他方を巻き込まない）', async () => {
    const fake = fakeCacheStorage()
    fake.failPutWith(new Error('put failed'))
    fake.failMatchWith(new Error('match failed'))
    const cache = new WorkersCache(fake.storage)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      await cache.set(testKey('a'), 'v', 60)
      await cache.get(testKey('a'))

      expect(warn).toHaveBeenCalledTimes(2)
    } finally {
      warn.mockRestore()
    }
  })

  it('直列化できない値（循環参照）では警告しない（Cache API の障害ではない）', async () => {
    const fake = fakeCacheStorage()
    const cache = new WorkersCache(fake.storage)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      const circular: { self?: unknown } = {}
      circular.self = circular
      await expect(cache.set(testKey('k'), circular, 60)).resolves.toBeUndefined()

      expect(warn).not.toHaveBeenCalled()
      expect(fake.puts).toHaveLength(0)
    } finally {
      warn.mockRestore()
    }
  })

  it('本文が壊れているだけでは警告しない（Cache API は生きている）', async () => {
    const fake = fakeCacheStorage()
    fake.seedRaw(cacheKeyToRequest(testKey('k')).url, 'not json', 60)
    const cache = new WorkersCache(fake.storage)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      await expect(cache.get(testKey('k'))).resolves.toBeNull()
      expect(warn).not.toHaveBeenCalled()
    } finally {
      warn.mockRestore()
    }
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
